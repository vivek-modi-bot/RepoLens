"""GitHub URL validation tests."""

import pytest
from pydantic import ValidationError

from app.core.exceptions import InvalidRepositoryURLError
from app.github.validator import is_valid_github_url, parse_github_url
from app.schemas.repository import RepositoryReviewRequest


def test_parse_valid_url() -> None:
    parsed = parse_github_url("https://github.com/owner/repository")
    assert parsed.owner == "owner"
    assert parsed.repo == "repository"
    assert parsed.normalized_url == "https://github.com/owner/repository"


def test_parse_url_with_git_suffix() -> None:
    parsed = parse_github_url("https://github.com/owner/repository.git")
    assert parsed.repo == "repository"


def test_parse_url_strips_extra_path() -> None:
    parsed = parse_github_url("https://github.com/owner/repository/tree/main")
    assert parsed.full_name == "owner/repository"


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/owner/repo",
        "git@github.com:owner/repo.git",
        "https://gitlab.com/owner/repo",
        "https://github.com/owner",
        "not-a-url",
        "https://github.com/owner/repo?tab=readme",
        "",
    ],
)
def test_invalid_urls(url: str) -> None:
    with pytest.raises(InvalidRepositoryURLError):
        parse_github_url(url)
    assert is_valid_github_url(url) is False


def test_schema_rejects_invalid_repository_url() -> None:
    with pytest.raises(ValidationError):
        RepositoryReviewRequest(
            repository_url="https://gitlab.com/owner/repo",
            review_type="full",
        )


def test_schema_accepts_valid_request() -> None:
    req = RepositoryReviewRequest(
        repository_url="https://github.com/psf/requests",
        branch="main",
        review_type="security",
    )
    assert req.owner == "psf"
    assert req.repo == "requests"
    assert req.review_type.value == "security"
