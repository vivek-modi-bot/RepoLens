"""Pydantic review schema and LLM parsing tests."""

import pytest
from pydantic import ValidationError

from app.analysis.aggregator import ReviewAggregator
from app.schemas.review import ChunkReviewResult, ReviewIssue, ReviewResponse
from app.services.llm_response_parser import extract_json_object, parse_chunk_review


def test_review_issue_validation() -> None:
    issue = ReviewIssue(
        file="src/auth.py",
        line=42,
        severity="high",
        category="security",
        title="Potential hardcoded credential",
        description="A secret appears embedded in source.",
        recommendation="Move secrets to environment variables.",
    )
    assert issue.severity.value == "high"


def test_review_issue_rejects_bad_severity() -> None:
    with pytest.raises(ValidationError):
        ReviewIssue(
            file="a.py",
            severity="urgent",
            category="security",
            title="x",
            description="y",
            recommendation="z",
        )


def test_parse_chunk_review_from_fenced_json() -> None:
    text = """
Here is the review:
```json
{
  "overall_score": 80,
  "summary": "Looks mostly fine",
  "issues": [
    {
      "file": "app.py",
      "line": 10,
      "severity": "medium",
      "category": "quality",
      "title": "Long function",
      "description": "Function is hard to maintain.",
      "recommendation": "Split into helpers."
    }
  ]
}
```
"""
    parsed = parse_chunk_review(text)
    assert parsed is not None
    assert parsed.overall_score == 80
    assert len(parsed.issues) == 1


def test_extract_json_object_invalid() -> None:
    assert extract_json_object("not json at all") is None


def test_parse_truncated_json_is_repaired() -> None:
    from app.services.llm_response_parser import parse_chunk_review

    text = (
        '{"overall_score":75,"summary":"Okay","issues":[{"file":"a.py","line":1,'
        '"severity":"low","category":"quality","title":"Smell","description":"Dup",'
        '"recommendation":"Refactor"'
    )
    parsed = parse_chunk_review(text)
    assert parsed is not None
    assert parsed.overall_score == 75
    assert len(parsed.issues) == 1


def test_parse_loose_issue_keys() -> None:
    from app.services.llm_response_parser import parse_chunk_review

    text = """
    {
      "overall_score": "90",
      "summary": "Fine",
      "findings": [
        {
          "path": "main.py",
          "message": "Missing type hints",
          "severity": "Low",
          "category": "code quality",
          "fix": "Add annotations"
        }
      ]
    }
    """
    parsed = parse_chunk_review(text)
    assert parsed is not None
    assert parsed.overall_score == 90
    assert parsed.issues[0].file == "main.py"
    assert parsed.issues[0].category.value == "quality"


def test_aggregator_deduplicates_issues() -> None:
    issue = ReviewIssue(
        file="a.py",
        line=1,
        severity="high",
        category="bug",
        title="Null deref",
        description="May crash",
        recommendation="Add guard",
    )
    results = [
        ChunkReviewResult(overall_score=70, summary="First", issues=[issue]),
        ChunkReviewResult(overall_score=80, summary="Second", issues=[issue]),
    ]
    aggregated = ReviewAggregator().aggregate(
        repository="owner/repo",
        branch="main",
        review_type="full",
        chunk_results=results,
        files_analyzed=2,
        languages=["Python"],
        total_lines=100,
        chunks_processed=2,
    )
    assert isinstance(aggregated, ReviewResponse)
    assert aggregated.statistics.issues_found == 1
    assert 70 <= aggregated.overall_score <= 80
