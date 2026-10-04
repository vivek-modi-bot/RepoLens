"""Aggregate and de-duplicate chunk-level review results."""

from __future__ import annotations

import statistics
from collections import OrderedDict

from app.schemas.review import (
    ChunkReviewResult,
    ReviewIssue,
    ReviewResponse,
    ReviewStatistics,
)


class ReviewAggregator:
    """Merge per-chunk LLM outputs into a single structured review."""

    def aggregate(
        self,
        *,
        repository: str,
        branch: str,
        review_type: str,
        chunk_results: list[ChunkReviewResult],
        files_analyzed: int,
        languages: list[str],
        total_lines: int,
        chunks_processed: int,
    ) -> ReviewResponse:
        issues = self._deduplicate_issues(
            [issue for result in chunk_results for issue in result.issues]
        )
        scores = [
            result.overall_score
            for result in chunk_results
            if result.overall_score is not None
        ]
        overall_score = int(round(statistics.mean(scores))) if scores else self._score_from_issues(issues)

        summaries = [
            result.summary.strip()
            for result in chunk_results
            if result.summary and result.summary.strip()
        ]
        summary = self._compose_summary(summaries, issues, overall_score)

        return ReviewResponse(
            repository=repository,
            branch=branch,
            review_type=review_type,
            overall_score=max(0, min(100, overall_score)),
            summary=summary,
            statistics=ReviewStatistics(
                files_analyzed=files_analyzed,
                languages=languages,
                issues_found=len(issues),
                total_lines=total_lines,
                chunks_processed=chunks_processed,
            ),
            issues=issues,
        )

    def _deduplicate_issues(self, issues: list[ReviewIssue]) -> list[ReviewIssue]:
        unique: OrderedDict[tuple, ReviewIssue] = OrderedDict()
        for issue in issues:
            key = (
                issue.file.strip().lower(),
                issue.line,
                issue.severity.value,
                issue.category.value,
                issue.title.strip().lower(),
            )
            if key not in unique:
                unique[key] = issue
        # Sort by severity weight then file/line.
        severity_order = {
            "critical": 0,
            "high": 1,
            "medium": 2,
            "low": 3,
            "info": 4,
        }
        return sorted(
            unique.values(),
            key=lambda i: (
                severity_order.get(i.severity.value, 99),
                i.file,
                i.line or 0,
            ),
        )

    def _score_from_issues(self, issues: list[ReviewIssue]) -> int:
        penalties = {
            "critical": 20,
            "high": 12,
            "medium": 6,
            "low": 3,
            "info": 1,
        }
        score = 100
        for issue in issues:
            score -= penalties.get(issue.severity.value, 3)
        return max(0, min(100, score))

    def _compose_summary(
        self,
        summaries: list[str],
        issues: list[ReviewIssue],
        overall_score: int,
    ) -> str:
        if summaries:
            # Prefer the first non-empty summary; append severity snapshot.
            base = summaries[0]
        else:
            base = (
                f"Automated review completed with score {overall_score}/100 "
                f"and {len(issues)} issue(s) identified."
            )

        critical = sum(1 for i in issues if i.severity.value == "critical")
        high = sum(1 for i in issues if i.severity.value == "high")
        if critical or high:
            base = (
                f"{base.rstrip()} "
                f"Priority focus: {critical} critical and {high} high severity findings."
            )
        return base[:2000]
