"""High-level repository fetch orchestration."""

from __future__ import annotations

import logging

from app.core.config import Settings, get_settings
from app.github.processor import FetchedRepository, RepositoryFetcher
from app.github.validator import ParsedGitHubURL, parse_github_url

logger = logging.getLogger(__name__)


class RepositoryService:
    """Validate URLs and fetch public repositories for analysis."""

    def __init__(
        self,
        settings: Settings | None = None,
        fetcher: RepositoryFetcher | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._fetcher = fetcher or RepositoryFetcher(self._settings)

    def parse_url(self, repository_url: str) -> ParsedGitHubURL:
        return parse_github_url(repository_url)

    async def fetch_repository(
        self,
        repository_url: str,
        branch: str | None = None,
    ) -> FetchedRepository:
        parsed = self.parse_url(repository_url)
        logger.info(
            "Fetching repository %s (branch=%s)",
            parsed.full_name,
            branch or "default",
        )
        return await self._fetcher.fetch(parsed, branch=branch)
