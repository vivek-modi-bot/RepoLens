"""Structured code-review response schemas."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class IssueCategory(str, Enum):
    BUG = "bug"
    SECURITY = "security"
    PERFORMANCE = "performance"
    MAINTAINABILITY = "maintainability"
    ARCHITECTURE = "architecture"
    QUALITY = "quality"
    STYLE = "style"
    OTHER = "other"


class ReviewIssue(BaseModel):
    file: str = Field(..., min_length=1, max_length=1024)
    line: int | None = Field(default=None, ge=1)
    severity: Severity
    category: IssueCategory
    title: str = Field(..., min_length=1, max_length=256)
    description: str = Field(..., min_length=1, max_length=4000)
    recommendation: str = Field(..., min_length=1, max_length=4000)

    @field_validator("severity", mode="before")
    @classmethod
    def normalize_severity(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.lower().strip()
        return value

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, value: Any) -> Any:
        if isinstance(value, str):
            normalized = value.lower().strip().replace(" ", "_")
            aliases = {
                "code_quality": "quality",
                "code-quality": "quality",
                "maintainability_issue": "maintainability",
                "perf": "performance",
                "sec": "security",
            }
            return aliases.get(normalized, normalized)
        return value


class ReviewStatistics(BaseModel):
    files_analyzed: int = Field(ge=0)
    languages: list[str] = Field(default_factory=list)
    issues_found: int = Field(ge=0)
    total_lines: int = Field(default=0, ge=0)
    chunks_processed: int = Field(default=0, ge=0)


class ChunkReviewResult(BaseModel):
    """Partial structured result returned by the LLM for one chunk."""

    overall_score: int | None = Field(default=None, ge=0, le=100)
    summary: str | None = None
    issues: list[ReviewIssue] = Field(default_factory=list)


class ReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    review_id: UUID | None = None
    repository: str
    branch: str
    review_type: str
    overall_score: int = Field(ge=0, le=100)
    summary: str
    statistics: ReviewStatistics
    issues: list[ReviewIssue] = Field(default_factory=list)
    created_at: datetime | None = None
    from_cache: bool = False
    chunks_reused: bool = False
    commit_sha: str | None = None


class ReviewSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    review_id: UUID
    repository: str
    branch: str
    review_type: str
    overall_score: int
    summary: str
    created_at: datetime
    issues_found: int = 0


class ReviewAskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    issue_index: int = Field(..., ge=0, description="Index of the finding in the review issues list")


class ReviewMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    issue_index: int = 0
    role: str
    content: str
    created_at: datetime


class ReviewAskResponse(BaseModel):
    review_id: UUID
    issue_index: int
    question: str
    answer: str
    messages: list[ReviewMessageResponse] = Field(default_factory=list)
