"""Repository review API routes."""

from uuid import UUID

from fastapi import APIRouter

from app.core.dependencies import CurrentUser, DbSession
from app.schemas.fix import (
    CreatePullRequestRequest,
    FixSuggestionResponse,
    PullRequestResponse,
)
from app.schemas.repository import RepositoryReviewRequest
from app.schemas.review import (
    ReviewAskRequest,
    ReviewAskResponse,
    ReviewMessageResponse,
    ReviewResponse,
    ReviewSummaryResponse,
)
from app.services.fix_service import FixService
from app.services.review_service import ReviewService

router = APIRouter(prefix="/repository", tags=["Repository Review"])


@router.post(
    "/review",
    response_model=ReviewResponse,
    summary="Analyze a public GitHub repository",
)
async def review_repository(
    payload: RepositoryReviewRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> ReviewResponse:
    """Download a public repository and produce a structured AI code review.

    Returns a previously saved review for the same user/repo/branch/type unless
    `force_refresh` is true. Chunk artifacts are reused by commit SHA when available.
    """
    service = ReviewService(db)
    return await service.review_repository(payload, current_user)


@router.get(
    "/reviews",
    response_model=list[ReviewSummaryResponse],
    summary="List previously saved reviews for the current user",
)
async def list_reviews(
    current_user: CurrentUser,
    db: DbSession,
) -> list[ReviewSummaryResponse]:
    service = ReviewService(db)
    return await service.list_reviews(current_user)


@router.get(
    "/{review_id}",
    response_model=ReviewResponse,
    summary="Fetch a previously stored review",
)
async def get_review(
    review_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> ReviewResponse:
    service = ReviewService(db)
    return await service.get_review(review_id, current_user)


@router.get(
    "/{review_id}/messages",
    response_model=list[ReviewMessageResponse],
    summary="List Q&A messages for a specific finding",
)
async def list_messages(
    review_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
    issue_index: int,
) -> list[ReviewMessageResponse]:
    service = ReviewService(db)
    return await service.list_messages(
        review_id, current_user, issue_index=issue_index
    )


@router.post(
    "/{review_id}/ask",
    response_model=ReviewAskResponse,
    summary="Ask a question about a specific finding",
)
async def ask_question(
    review_id: UUID,
    payload: ReviewAskRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> ReviewAskResponse:
    service = ReviewService(db)
    return await service.ask_question(
        review_id,
        current_user,
        payload.question,
        issue_index=payload.issue_index,
    )


@router.post(
    "/{review_id}/findings/{issue_index}/fix",
    response_model=FixSuggestionResponse,
    summary="Generate a code fix for a specific finding",
)
async def generate_finding_fix(
    review_id: UUID,
    issue_index: int,
    current_user: CurrentUser,
    db: DbSession,
) -> FixSuggestionResponse:
    service = FixService(db)
    return await service.generate_fix(
        review_id=review_id,
        issue_index=issue_index,
        user=current_user,
    )


@router.get(
    "/{review_id}/findings/{issue_index}/fix",
    response_model=FixSuggestionResponse,
    summary="Get the latest generated fix for a finding",
)
async def get_finding_fix(
    review_id: UUID,
    issue_index: int,
    current_user: CurrentUser,
    db: DbSession,
) -> FixSuggestionResponse:
    service = FixService(db)
    return await service.get_latest_fix(
        review_id=review_id,
        issue_index=issue_index,
        user=current_user,
    )


@router.post(
    "/{review_id}/findings/{issue_index}/pull-request",
    response_model=PullRequestResponse,
    summary="Create a GitHub pull request for a generated fix",
)
async def create_finding_pull_request(
    review_id: UUID,
    issue_index: int,
    payload: CreatePullRequestRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> PullRequestResponse:
    """Requires a GitHub PAT with repo write access. The token is not stored."""
    service = FixService(db)
    return await service.create_pull_request(
        review_id=review_id,
        issue_index=issue_index,
        user=current_user,
        payload=payload,
    )
