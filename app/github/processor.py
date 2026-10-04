"""Download and extract public GitHub repositories safely."""

from __future__ import annotations

import logging
import shutil
import tarfile
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from app.core.config import Settings, get_settings
from app.core.exceptions import RepositoryNotFoundError, RepositoryTooLargeError
from app.github.client import GitHubClient
from app.github.validator import ParsedGitHubURL

logger = logging.getLogger(__name__)


@dataclass
class FetchedRepository:
    """Result of downloading a public repository archive."""

    owner: str
    repo: str
    branch: str
    root_path: Path
    temp_dir: Path
    size_bytes: int
    metadata: dict = field(default_factory=dict)

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"

    def cleanup(self) -> None:
        """Remove temporary files created for this fetch."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            logger.info("Cleaned up temporary repository directory %s", self.temp_dir)


class RepositoryFetcher:
    """
    Fetch public repositories via GitHub's tarball API.

    IMPORTANT: This service never executes repository code. It only downloads
    and extracts source archives for static analysis.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        github_client: GitHubClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._github_client = github_client

    async def fetch(
        self,
        parsed: ParsedGitHubURL,
        branch: str | None = None,
    ) -> FetchedRepository:
        """Download and extract a repository into a temporary directory."""
        base_temp = Path(self._settings.temp_dir)
        base_temp.mkdir(parents=True, exist_ok=True)
        work_dir = Path(tempfile.mkdtemp(prefix=f"repo-{uuid.uuid4().hex}-", dir=base_temp))

        try:
            async with (self._github_client or GitHubClient(self._settings)) as client:
                metadata = await client.get_repository(parsed)
                resolved_branch = await client.resolve_branch(parsed, branch)
                tarball_url = await client.get_tarball_url(parsed, resolved_branch)

                archive_path = work_dir / "repo.tar.gz"
                extract_dir = work_dir / "src"
                extract_dir.mkdir(parents=True, exist_ok=True)

                size_bytes = await self._download_archive(
                    client.client, tarball_url, archive_path
                )
                root_path = self._safe_extract(archive_path, extract_dir)

                # Archive no longer needed.
                archive_path.unlink(missing_ok=True)

                return FetchedRepository(
                    owner=parsed.owner,
                    repo=parsed.repo,
                    branch=resolved_branch,
                    root_path=root_path,
                    temp_dir=work_dir,
                    size_bytes=size_bytes,
                    metadata=metadata,
                )
        except Exception:
            shutil.rmtree(work_dir, ignore_errors=True)
            raise

    async def _download_archive(
        self,
        client: httpx.AsyncClient,
        url: str,
        destination: Path,
    ) -> int:
        max_size = self._settings.max_repository_size
        downloaded = 0

        try:
            async with client.stream(
                "GET",
                url,
                follow_redirects=True,
                timeout=self._settings.clone_timeout_seconds,
            ) as response:
                if response.status_code == 404:
                    raise RepositoryNotFoundError("Repository archive not found")
                response.raise_for_status()

                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > max_size:
                    raise RepositoryTooLargeError(
                        f"Repository archive exceeds limit of {max_size} bytes"
                    )

                with destination.open("wb") as handle:
                    async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                        downloaded += len(chunk)
                        if downloaded > max_size:
                            raise RepositoryTooLargeError(
                                f"Repository archive exceeds limit of {max_size} bytes"
                            )
                        handle.write(chunk)
        except httpx.HTTPError as exc:
            logger.exception("Failed to download repository archive")
            raise RepositoryNotFoundError(
                "Failed to download repository archive"
            ) from exc

        logger.info("Downloaded repository archive (%s bytes)", downloaded)
        return downloaded

    def _safe_extract(self, archive_path: Path, extract_dir: Path) -> Path:
        """Extract a tarball while guarding against path traversal."""
        with tarfile.open(archive_path, "r:gz") as tar:
            members = tar.getmembers()
            total_uncompressed = 0
            safe_members: list[tarfile.TarInfo] = []

            for member in members:
                member_path = Path(member.name)
                if member_path.is_absolute() or ".." in member_path.parts:
                    logger.warning("Skipping unsafe archive member: %s", member.name)
                    continue

                total_uncompressed += max(member.size, 0)
                if total_uncompressed > self._settings.max_repository_size * 2:
                    raise RepositoryTooLargeError(
                        "Uncompressed repository exceeds size limits"
                    )
                safe_members.append(member)

            # Python 3.12+ supports filter=; use it when available.
            try:
                tar.extractall(path=extract_dir, members=safe_members, filter="data")
            except TypeError:
                tar.extractall(path=extract_dir, members=safe_members)

        children = [p for p in extract_dir.iterdir() if p.is_dir()]
        if len(children) == 1:
            return children[0]
        return extract_dir
