"""Authenticated GitHub helpers for creating branches, commits, and PRs."""

from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.exceptions import GitHubWriteError, RepositoryNotFoundError

logger = logging.getLogger(__name__)


class GitHubPRClient:
    """Write-capable GitHub client using a short-lived user-provided token."""

    def __init__(
        self,
        token: str,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._token = token.strip()
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> GitHubPRClient:
        self._client = httpx.AsyncClient(
            base_url=self._settings.github_api_base_url,
            timeout=self._settings.github_timeout_seconds,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "User-Agent": f"{self._settings.app_name}/{self._settings.app_version}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("GitHubPRClient must be used as an async context manager")
        return self._client

    async def get_file_content(
        self, owner: str, repo: str, path: str, ref: str
    ) -> tuple[str, str]:
        """Return (decoded_text, sha) for a file at ref. Auth optional for public repos."""
        response = await self.client.get(
            f"/repos/{owner}/{repo}/contents/{path}",
            params={"ref": ref},
        )
        if response.status_code == 404:
            raise RepositoryNotFoundError(f"File '{path}' not found on branch '{ref}'")
        if response.status_code >= 400:
            raise GitHubWriteError(
                f"Unable to read '{path}' from GitHub ({response.status_code})"
            )
        data = response.json()
        if data.get("type") != "file":
            raise GitHubWriteError(f"Path '{path}' is not a file")
        encoded = data.get("content") or ""
        sha = data.get("sha") or ""
        # GitHub may omit content for large files; fall back to download_url.
        if not encoded and data.get("download_url"):
            raw = await self.client.get(data["download_url"])
            raw.raise_for_status()
            return raw.text, sha
        try:
            text = base64.b64decode(encoded).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise GitHubWriteError(
                f"File '{path}' could not be decoded as UTF-8 text"
            ) from exc
        return text, sha

    async def get_branch_sha(self, owner: str, repo: str, branch: str) -> str:
        response = await self.client.get(f"/repos/{owner}/{repo}/git/ref/heads/{branch}")
        if response.status_code == 404:
            raise RepositoryNotFoundError(f"Branch '{branch}' not found")
        if response.status_code >= 400:
            raise GitHubWriteError(
                "Unable to resolve branch head. Check repository access for this token."
            )
        data = response.json()
        sha = (data.get("object") or {}).get("sha")
        if not sha:
            raise GitHubWriteError("GitHub did not return a branch SHA")
        return sha

    async def create_branch(
        self, owner: str, repo: str, branch_name: str, from_sha: str
    ) -> None:
        response = await self.client.post(
            f"/repos/{owner}/{repo}/git/refs",
            json={"ref": f"refs/heads/{branch_name}", "sha": from_sha},
        )
        if response.status_code in {422, 409}:
            # Branch may already exist; move it forward.
            update = await self.client.patch(
                f"/repos/{owner}/{repo}/git/refs/heads/{branch_name}",
                json={"sha": from_sha, "force": True},
            )
            if update.status_code >= 400:
                raise GitHubWriteError(
                    f"Unable to create or update branch '{branch_name}'. "
                    "Ensure the token can write to this repository."
                )
            return
        if response.status_code >= 400:
            detail = _safe_message(response)
            raise GitHubWriteError(
                f"Unable to create branch '{branch_name}': {detail}"
            )

    async def commit_file(
        self,
        *,
        owner: str,
        repo: str,
        path: str,
        content: str,
        message: str,
        branch: str,
        current_sha: str | None,
    ) -> str:
        payload: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if current_sha:
            payload["sha"] = current_sha

        response = await self.client.put(
            f"/repos/{owner}/{repo}/contents/{path}",
            json=payload,
        )
        if response.status_code >= 400:
            detail = _safe_message(response)
            raise GitHubWriteError(
                "Unable to commit file change. "
                "The token needs write access to the repository. "
                f"GitHub said: {detail}"
            )
        data = response.json()
        commit_sha = ((data.get("commit") or {}).get("sha")) or ""
        return commit_sha

    async def create_pull_request(
        self,
        *,
        owner: str,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> dict[str, Any]:
        response = await self.client.post(
            f"/repos/{owner}/{repo}/pulls",
            json={
                "title": title,
                "body": body,
                "head": head,
                "base": base,
            },
        )
        if response.status_code >= 400:
            detail = _safe_message(response)
            raise GitHubWriteError(
                "Unable to open pull request. "
                "Confirm the token can create PRs on this repository. "
                f"GitHub said: {detail}"
            )
        return response.json()


def _safe_message(response: httpx.Response) -> str:
    try:
        data = response.json()
        message = data.get("message")
        errors = data.get("errors")
        if message and errors:
            return f"{message} ({errors})"
        if message:
            return str(message)
    except Exception:  # noqa: BLE001
        pass
    return response.text[:240] or f"HTTP {response.status_code}"
