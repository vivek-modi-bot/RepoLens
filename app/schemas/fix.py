"""Schemas for AI code fixes and pull-request creation."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FixSuggestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fix_id: str
    review_id: str
    issue_index: int
    file_path: str
    original_content: str
    updated_content: str
    explanation: str
    commit_message: str
    pr_url: str | None = None
    pr_number: int | None = None
    created_at: datetime | None = None


class CreatePullRequestRequest(BaseModel):
    github_token: str | None = Field(
        default=None,
        min_length=8,
        max_length=512,
        description=(
            "Optional GitHub PAT override. If omitted, the encrypted token "
            "saved on the user profile is used."
        ),
    )
    fix_id: str | None = Field(
        default=None,
        description="Optional fix id; defaults to the latest fix for this finding",
    )
    branch_name: str | None = Field(
        default=None,
        max_length=120,
        description="Optional branch name for the fix",
    )
    pr_title: str | None = Field(default=None, max_length=200)
    pr_body: str | None = Field(default=None, max_length=4000)


class PullRequestResponse(BaseModel):
    fix_id: str
    review_id: str
    issue_index: int
    branch_name: str
    pr_number: int
    pr_url: str
    commit_sha: str
