"""End-to-end repository review orchestration."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.aggregator import ReviewAggregator
from app.analysis.chunker import CodeChunk, CodeChunker
from app.analysis.file_filter import FileFilter
from app.analysis.language_detector import LanguageDetector
from app.core.config import Settings, get_settings
from app.core.exceptions import (
    FindingNotFoundError,
    LLMResponseError,
    ReviewNotFoundError,
)
from app.github.client import GitHubClient
from app.github.validator import parse_github_url
from app.llm.base import LLMProvider, build_llm_provider
from app.models.chunk_cache import ChunkCache
from app.models.review import Review
from app.models.review_message import ReviewMessage
from app.models.user import User
from app.schemas.repository import RepositoryReviewRequest, ReviewType
from app.schemas.review import (
    ChunkReviewResult,
    ReviewAskResponse,
    ReviewMessageResponse,
    ReviewResponse,
    ReviewStatistics,
    ReviewSummaryResponse,
)
from app.services.llm_response_parser import parse_chunk_review
from app.services.prompt_service import PromptService
from app.services.repository_service import RepositoryService

logger = logging.getLogger(__name__)


class ReviewService:
    """
    Pipeline:
      RepositoryFetcher → FileFilter → LanguageDetector → CodeChunker
      → LLMProvider → ReviewAggregator → StructuredReviewResponse

    Cached reviews and chunk artifacts are reused when possible.
    """

    def __init__(
        self,
        db: AsyncSession,
        settings: Settings | None = None,
        repository_service: RepositoryService | None = None,
        llm_provider: LLMProvider | None = None,
        file_filter: FileFilter | None = None,
        language_detector: LanguageDetector | None = None,
        chunker: CodeChunker | None = None,
        aggregator: ReviewAggregator | None = None,
        prompt_service: PromptService | None = None,
    ) -> None:
        self._db = db
        self._settings = settings or get_settings()
        self._repository_service = repository_service or RepositoryService(self._settings)
        self._llm = llm_provider or build_llm_provider(self._settings)
        self._file_filter = file_filter or FileFilter(self._settings)
        self._language_detector = language_detector or LanguageDetector()
        self._chunker = chunker or CodeChunker(self._settings)
        self._aggregator = aggregator or ReviewAggregator()
        self._prompts = prompt_service or PromptService()

    async def review_repository(
        self,
        request: RepositoryReviewRequest,
        user: User,
    ) -> ReviewResponse:
        parsed = parse_github_url(request.repository_url)

        async with GitHubClient(self._settings) as github:
            branch, commit_sha = await github.resolve_branch_and_sha(
                parsed, request.branch
            )

        if not request.force_refresh:
            cached_review = await self._find_cached_review(
                user=user,
                repository=parsed.full_name,
                branch=branch,
                review_type=request.review_type.value,
            )
            if cached_review is not None:
                logger.info(
                    "Returning cached review %s for %s@%s (%s)",
                    cached_review.id,
                    parsed.full_name,
                    branch,
                    request.review_type.value,
                )
                response = self._to_response(cached_review)
                response.from_cache = True
                response.chunks_reused = True
                response.commit_sha = commit_sha
                return response

        chunks, stats, chunks_reused = await self._get_or_build_chunks(
            repository=parsed.full_name,
            repository_url=request.repository_url,
            branch=branch,
            commit_sha=commit_sha,
        )

        try:
            response = await self._analyze_chunks(
                repository=parsed.full_name,
                branch=branch,
                review_type=request.review_type,
                chunks=chunks,
                stats=stats,
            )
            response.chunks_reused = chunks_reused
            response.commit_sha = commit_sha
            persisted = await self._persist(user=user, response=response)
            response.review_id = UUID(persisted.id)
            response.created_at = persisted.created_at
            response.from_cache = False
            return response
        finally:
            await self._llm.aclose()

    async def list_reviews(self, user: User) -> list[ReviewSummaryResponse]:
        result = await self._db.execute(
            select(Review)
            .where(Review.user_id == user.id)
            .order_by(Review.created_at.desc())
        )
        reviews = result.scalars().all()
        return [
            ReviewSummaryResponse(
                review_id=UUID(review.id),
                repository=review.repository,
                branch=review.branch,
                review_type=review.review_type,
                overall_score=review.overall_score,
                summary=review.summary,
                created_at=review.created_at,
                issues_found=int((review.statistics or {}).get("issues_found") or 0),
            )
            for review in reviews
        ]

    async def get_review(self, review_id: UUID, user: User) -> ReviewResponse:
        review = await self._get_owned_review(review_id, user)
        return self._to_response(review)

    async def list_messages(
        self,
        review_id: UUID,
        user: User,
        issue_index: int | None = None,
    ) -> list[ReviewMessageResponse]:
        await self._get_owned_review(review_id, user)
        query = select(ReviewMessage).where(ReviewMessage.review_id == str(review_id))
        if issue_index is not None:
            query = query.where(ReviewMessage.issue_index == issue_index)
        result = await self._db.execute(query.order_by(ReviewMessage.created_at.asc()))
        messages = result.scalars().all()
        return [
            ReviewMessageResponse(
                id=message.id,
                issue_index=message.issue_index,
                role=message.role,
                content=message.content,
                created_at=message.created_at,
            )
            for message in messages
        ]

    async def ask_question(
        self,
        review_id: UUID,
        user: User,
        question: str,
        issue_index: int,
    ) -> ReviewAskResponse:
        review = await self._get_owned_review(review_id, user)
        issues = list(review.issues or [])
        if issue_index < 0 or issue_index >= len(issues):
            raise FindingNotFoundError(
                f"Finding index {issue_index} is not available on this review"
            )

        issue = issues[issue_index]
        history_rows = await self.list_messages(
            review_id, user, issue_index=issue_index
        )
        history = [(row.role, row.content) for row in history_rows]

        prompt = self._prompts.build_ask_prompt(
            repository=review.repository,
            branch=review.branch,
            review_type=review.review_type,
            summary=review.summary,
            issue=dict(issue),
            question=question.strip(),
            history=history,
        )

        try:
            answer = await self._llm.generate_text(prompt)
        finally:
            await self._llm.aclose()

        user_msg = ReviewMessage(
            review_id=str(review_id),
            issue_index=issue_index,
            role="user",
            content=question.strip(),
            created_at=datetime.now(UTC),
        )
        assistant_msg = ReviewMessage(
            review_id=str(review_id),
            issue_index=issue_index,
            role="assistant",
            content=answer,
            created_at=datetime.now(UTC),
        )
        self._db.add(user_msg)
        self._db.add(assistant_msg)
        await self._db.commit()

        messages = await self.list_messages(review_id, user, issue_index=issue_index)
        return ReviewAskResponse(
            review_id=review_id,
            issue_index=issue_index,
            question=question.strip(),
            answer=answer,
            messages=messages,
        )

    async def _find_cached_review(
        self,
        *,
        user: User,
        repository: str,
        branch: str,
        review_type: str,
    ) -> Review | None:
        result = await self._db.execute(
            select(Review)
            .where(
                Review.user_id == user.id,
                Review.repository == repository,
                Review.branch == branch,
                Review.review_type == review_type,
            )
            .order_by(Review.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_or_build_chunks(
        self,
        *,
        repository: str,
        repository_url: str,
        branch: str,
        commit_sha: str,
    ) -> tuple[list[CodeChunk], dict, bool]:
        cached = await self._db.execute(
            select(ChunkCache).where(
                ChunkCache.repository == repository,
                ChunkCache.branch == branch,
                ChunkCache.commit_sha == commit_sha,
            )
        )
        row = cached.scalar_one_or_none()
        if row is not None and row.chunks:
            logger.info(
                "Reusing cached chunks for %s@%s (%s) — %s chunks",
                repository,
                branch,
                commit_sha[:8],
                len(row.chunks),
            )
            chunks = [
                CodeChunk(
                    chunk_id=item.get("chunk_id", f"chunk-{index}"),
                    files=list(item.get("files") or []),
                    content=item.get("content") or "",
                    language=item.get("language"),
                    char_count=int(item.get("char_count") or 0),
                )
                for index, item in enumerate(row.chunks)
                if item.get("content")
            ]
            return chunks, dict(row.statistics or {}), True

        fetched = await self._repository_service.fetch_repository(
            repository_url,
            branch=branch,
        )
        try:
            files = self._file_filter.collect(fetched.root_path)
            files = self._language_detector.annotate(files)
            stats = self._language_detector.statistics(files)
            chunks = self._chunker.chunk_files(files)
            await self._save_chunk_cache(
                repository=repository,
                branch=branch,
                commit_sha=commit_sha,
                chunks=chunks,
                statistics=stats,
            )
            return chunks, stats, False
        finally:
            fetched.cleanup()

    async def _save_chunk_cache(
        self,
        *,
        repository: str,
        branch: str,
        commit_sha: str,
        chunks: list[CodeChunk],
        statistics: dict,
    ) -> None:
        payload = [
            {
                "chunk_id": chunk.chunk_id,
                "files": chunk.files,
                "content": chunk.content,
                "language": chunk.language,
                "char_count": chunk.char_count,
            }
            for chunk in chunks
        ]
        existing = await self._db.execute(
            select(ChunkCache).where(
                ChunkCache.repository == repository,
                ChunkCache.branch == branch,
                ChunkCache.commit_sha == commit_sha,
            )
        )
        row = existing.scalar_one_or_none()
        if row is None:
            row = ChunkCache(
                repository=repository,
                branch=branch,
                commit_sha=commit_sha,
                chunks=payload,
                statistics=statistics,
                created_at=datetime.now(UTC),
            )
            self._db.add(row)
        else:
            row.chunks = payload
            row.statistics = statistics
        await self._db.commit()

    async def _analyze_chunks(
        self,
        *,
        repository: str,
        branch: str,
        review_type: ReviewType,
        chunks: list[CodeChunk],
        stats: dict,
    ) -> ReviewResponse:
        logger.info(
            "Analyzing %s@%s: %s files, %s chunks, type=%s",
            repository,
            branch,
            stats.get("files_analyzed", 0),
            len(chunks),
            review_type.value,
        )

        if not chunks:
            return ReviewResponse(
                repository=repository,
                branch=branch,
                review_type=review_type.value,
                overall_score=100,
                summary="No analyzable source files were found after filtering.",
                statistics=ReviewStatistics(
                    files_analyzed=0,
                    languages=[],
                    issues_found=0,
                    total_lines=0,
                    chunks_processed=0,
                ),
                issues=[],
            )

        chunk_results: list[ChunkReviewResult] = []
        total_chunks = len(chunks)
        for index, chunk in enumerate(chunks, start=1):
            logger.info(
                "Reviewing chunk %s/%s (%s files, %s chars)",
                index,
                total_chunks,
                len(chunk.files),
                chunk.char_count,
            )
            prompt = self._prompts.build_chunk_prompt(
                review_type=review_type,
                repository=repository,
                branch=branch,
                chunk_content=chunk.content,
                chunk_files=chunk.files,
            )
            try:
                result = await self._generate_validated(prompt)
            except LLMResponseError:
                logger.warning(
                    "Skipping chunk %s/%s due to invalid LLM JSON",
                    index,
                    total_chunks,
                )
                result = ChunkReviewResult(
                    overall_score=None,
                    summary=None,
                    issues=[],
                )
            chunk_results.append(result)

        if all(not result.issues and result.summary is None for result in chunk_results):
            chunk_results = [
                ChunkReviewResult(
                    overall_score=70,
                    summary=(
                        "The model reviewed the repository, but structured findings "
                        "could not be reliably parsed from one or more chunks. "
                        "Try a smaller repository or a stronger model."
                    ),
                    issues=[],
                )
            ]

        return self._aggregator.aggregate(
            repository=repository,
            branch=branch,
            review_type=review_type.value,
            chunk_results=chunk_results,
            files_analyzed=int(stats.get("files_analyzed") or 0),
            languages=list(stats.get("languages") or []),
            total_lines=int(stats.get("total_lines") or 0),
            chunks_processed=len(chunks),
        )

    async def _generate_validated(self, prompt: str) -> ChunkReviewResult:
        raw = await self._llm.generate_review(prompt)
        parsed = parse_chunk_review(raw)
        if parsed is not None:
            return parsed

        for attempt in range(self._settings.llm_max_retries):
            logger.warning("Retrying LLM parse (attempt %s)", attempt + 1)
            retry_prompt = self._prompts.build_retry_prompt(raw)
            raw = await self._llm.generate_review(retry_prompt)
            parsed = parse_chunk_review(raw)
            if parsed is not None:
                return parsed

        raise LLMResponseError(
            "LLM returned an invalid structured response after retries"
        )

    async def _persist(self, *, user: User, response: ReviewResponse) -> Review:
        review = Review(
            user_id=user.id,
            repository=response.repository,
            branch=response.branch,
            review_type=response.review_type,
            overall_score=response.overall_score,
            summary=response.summary,
            statistics=response.statistics.model_dump(),
            issues=[issue.model_dump() for issue in response.issues],
            created_at=datetime.now(UTC),
        )
        self._db.add(review)
        await self._db.commit()
        await self._db.refresh(review)
        return review

    async def _get_owned_review(self, review_id: UUID, user: User) -> Review:
        result = await self._db.execute(
            select(Review).where(
                Review.id == str(review_id),
                Review.user_id == user.id,
            )
        )
        review = result.scalar_one_or_none()
        if review is None:
            raise ReviewNotFoundError()
        return review

    def _to_response(self, review: Review) -> ReviewResponse:
        return ReviewResponse(
            review_id=UUID(review.id),
            repository=review.repository,
            branch=review.branch,
            review_type=review.review_type,
            overall_score=review.overall_score,
            summary=review.summary,
            statistics=review.statistics,
            issues=review.issues,
            created_at=review.created_at,
            from_cache=False,
            chunks_reused=False,
        )
