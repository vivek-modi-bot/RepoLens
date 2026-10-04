"""Repository review request schemas."""

from enum import Enum
from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator

from app.github.validator import parse_github_url


class ReviewType(str, Enum):
    FULL = "full"
    SECURITY = "security"
    PERFORMANCE = "performance"
    QUALITY = "quality"
    ARCHITECTURE = "architecture"


class RepositoryReviewRequest(BaseModel):
    repository_url: str = Field(
        ...,
        description="Public GitHub repository URL",
        examples=["https://github.com/owner/repository"],
    )
    branch: str | None = Field(
        default=None,
        max_length=255,
        description="Optional branch name (defaults to the repository default branch)",
    )
    review_type: ReviewType = ReviewType.FULL
    force_refresh: bool = Field(
        default=False,
        description="If true, re-run analysis even when a cached review exists",
    )

    @field_validator("repository_url")
    @classmethod
    def validate_github_url(cls, value: str) -> str:
        from app.core.exceptions import InvalidRepositoryURLError

        try:
            parsed = parse_github_url(value)
        except InvalidRepositoryURLError as exc:
            # Pydantic expects ValueError for field validation failures.
            raise ValueError(str(exc)) from exc
        return parsed.normalized_url

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cleaned = value.strip()
        if not cleaned:
            return None
        if any(ch in cleaned for ch in (" ", "..", "\\")):
            raise ValueError("Invalid branch name")
        return cleaned

    @model_validator(mode="after")
    def attach_parsed_repo(self) -> Self:
        # Validation already ran; keep attribute for downstream convenience.
        object.__setattr__(self, "_parsed", parse_github_url(self.repository_url))
        return self

    @property
    def owner(self) -> str:
        return parse_github_url(self.repository_url).owner

    @property
    def repo(self) -> str:
        return parse_github_url(self.repository_url).repo
