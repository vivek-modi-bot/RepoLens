"""GitHub repository URL validation and parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from app.core.exceptions import InvalidRepositoryURLError

# Accept https://github.com/owner/repo[.git][/...] with optional trailing slash.
_GITHUB_PATH_RE = re.compile(
    r"^/(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38})"
    r"/(?P<repo>[A-Za-z0-9._-]{1,100})(?:\.git)?/?$"
)


@dataclass(frozen=True, slots=True)
class ParsedGitHubURL:
    owner: str
    repo: str
    normalized_url: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"


def parse_github_url(url: str) -> ParsedGitHubURL:
    """Parse and validate a public GitHub repository URL.

    Only `https://github.com/owner/repo` style URLs are accepted.
    SSH URLs, gist URLs, and non-GitHub hosts are rejected.
    """
    if not url or not isinstance(url, str):
        raise InvalidRepositoryURLError("Repository URL is required")

    cleaned = url.strip()
    parsed = urlparse(cleaned)

    if parsed.scheme != "https":
        raise InvalidRepositoryURLError("Only HTTPS GitHub URLs are supported")

    if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
        raise InvalidRepositoryURLError("URL must point to github.com")

    if parsed.query or parsed.fragment:
        raise InvalidRepositoryURLError("Repository URL must not include query or fragment")

    # Strip extra path segments like /tree/main or /blob/...
    path = parsed.path.rstrip("/")
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        raise InvalidRepositoryURLError("URL must be of the form https://github.com/owner/repo")

    owner, repo = parts[0], parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]

    candidate = f"/{owner}/{repo}"
    match = _GITHUB_PATH_RE.match(candidate)
    if not match:
        raise InvalidRepositoryURLError("Invalid GitHub owner or repository name")

    owner = match.group("owner")
    repo = match.group("repo")

    if owner.lower() in {"orgs", "users", "settings", "marketplace", "topics", "explore"}:
        raise InvalidRepositoryURLError("URL does not reference a repository")

    normalized = f"https://github.com/{owner}/{repo}"
    return ParsedGitHubURL(owner=owner, repo=repo, normalized_url=normalized)


def is_valid_github_url(url: str) -> bool:
    """Return True if the URL is a valid public GitHub repository URL."""
    try:
        parse_github_url(url)
        return True
    except InvalidRepositoryURLError:
        return False
