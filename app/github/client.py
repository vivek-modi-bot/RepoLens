"""Lightweight GitHub API client for public repositories."""

from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.exceptions import RepositoryNotFoundError
from app.github.validator import ParsedGitHubURL

logger = logging.getLogger(__name__)


class GitHubClient:
    """Read-only client for public GitHub repository metadata."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> GitHubClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._settings.github_api_base_url,
                timeout=self._settings.github_timeout_seconds,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": f"{self._settings.app_name}/{self._settings.app_version}",
                },
            )
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("GitHubClient must be used as an async context manager")
        return self._client

    async def get_repository(self, parsed: ParsedGitHubURL) -> dict[str, Any]:
        """Fetch public repository metadata. Raises if private/missing."""
        response = await self.client.get(f"/repos/{parsed.owner}/{parsed.repo}")

        if response.status_code == 404:
            raise RepositoryNotFoundError(
                f"Repository '{parsed.full_name}' was not found or is private"
            )
        if response.status_code == 403:
            # Could be rate-limited or blocked; treat as not accessible.
            raise RepositoryNotFoundError(
                f"Repository '{parsed.full_name}' is not accessible"
            )
        response.raise_for_status()
        data = response.json()

        if data.get("private") is True:
            raise RepositoryNotFoundError(
                "Only public GitHub repositories are supported"
            )
        return data

    async def resolve_branch(
        self, parsed: ParsedGitHubURL, branch: str | None
    ) -> str:
        """Resolve the branch to analyze (requested or repository default)."""
        resolved, _ = await self.resolve_branch_and_sha(parsed, branch)
        return resolved

    async def resolve_branch_and_sha(
        self, parsed: ParsedGitHubURL, branch: str | None
    ) -> tuple[str, str]:
        """Resolve branch name and head commit SHA."""
        repo = await self.get_repository(parsed)
        default_branch = repo.get("default_branch") or "main"
        target = branch or default_branch

        ref_response = await self.client.get(
            f"/repos/{parsed.owner}/{parsed.repo}/branches/{target}"
        )
        if ref_response.status_code == 404:
            raise RepositoryNotFoundError(
                f"Branch '{target}' not found in '{parsed.full_name}'"
            )
        ref_response.raise_for_status()
        payload = ref_response.json()
        sha = (payload.get("commit") or {}).get("sha") or "unknown"
        return target, sha

    async def get_tarball_url(self, parsed: ParsedGitHubURL, branch: str) -> str:
        """Return the GitHub archive tarball URL for a branch."""
        # Ensure repo exists / is public first.
        await self.get_repository(parsed)
        return (
            f"{self._settings.github_api_base_url}"
            f"/repos/{parsed.owner}/{parsed.repo}/tarball/{branch}"
        )

    async def get_file_text(
        self, parsed: ParsedGitHubURL, path: str, ref: str
    ) -> str:
        """Fetch a text file from a public repository branch/ref."""
        response = await self.client.get(
            f"/repos/{parsed.owner}/{parsed.repo}/contents/{path}",
            params={"ref": ref},
        )
        if response.status_code == 404:
            raise RepositoryNotFoundError(
                f"File '{path}' was not found on branch '{ref}'"
            )
        response.raise_for_status()
        data = response.json()
        if data.get("type") != "file":
            raise RepositoryNotFoundError(f"Path '{path}' is not a file")
        encoded = data.get("content") or ""
        if encoded:
            return base64.b64decode(encoded).decode("utf-8", errors="replace")
        download_url = data.get("download_url")
        if not download_url:
            raise RepositoryNotFoundError(f"File '{path}' content is unavailable")
        raw = await self.client.get(download_url)
        raw.raise_for_status()
        return raw.text
