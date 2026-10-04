"""Safe parsing of structured LLM JSON responses."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import ValidationError

from app.schemas.review import ChunkReviewResult, ReviewIssue

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


def _strip_trailing_commas(text: str) -> str:
    return re.sub(r",(\s*[}\]])", r"\1", text)


def _balance_json(text: str) -> str:
    """Best-effort close truncated JSON objects/arrays."""
    in_string = False
    escape = False
    stack: list[str] = []

    for ch in text:
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if stack and stack[-1] == ch:
                stack.pop()

    repaired = text
    if in_string:
        repaired += '"'
    while stack:
        repaired += stack.pop()
    return repaired


def extract_json_object(text: str) -> dict[str, Any] | None:
    """Best-effort extraction of a JSON object from model output."""
    if not text:
        return None

    candidates: list[str] = [text.strip()]

    fenced = _JSON_FENCE_RE.search(text)
    if fenced:
        candidates.insert(0, fenced.group(1).strip())

    start = text.find("{")
    end = text.rfind("}")
    if start != -1:
        if end != -1 and end > start:
            candidates.append(text[start : end + 1])
        candidates.append(text[start:])

    # Some models wrap the object in an array.
    array_start = text.find("[")
    if array_start != -1:
        candidates.append(text[array_start:])

    seen: set[str] = set()
    for candidate in candidates:
        variants = [
            candidate,
            _strip_trailing_commas(candidate),
            _balance_json(_strip_trailing_commas(candidate)),
        ]
        for variant in variants:
            cleaned = variant.strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            try:
                parsed = json.loads(cleaned)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        return item
    return None


def _coerce_score(value: Any) -> int | None:
    if value is None:
        return None
    try:
        score = int(float(value))
    except (TypeError, ValueError):
        return None
    return max(0, min(100, score))


def _coerce_issue(item: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize loose issue dicts from small models into schema-compatible data."""
    normalized = dict(item)

    # Common alternate keys
    if "file" not in normalized:
        for key in ("path", "filename", "filepath", "file_path"):
            if key in normalized:
                normalized["file"] = normalized[key]
                break
    if "title" not in normalized:
        for key in ("name", "issue", "problem", "message"):
            if key in normalized:
                normalized["title"] = normalized[key]
                break
    if "description" not in normalized:
        for key in ("detail", "details", "explanation", "reason", "message"):
            if key in normalized and key != "title":
                normalized["description"] = normalized[key]
                break
    if "recommendation" not in normalized:
        for key in ("fix", "suggestion", "remediation", "solution", "advice"):
            if key in normalized:
                normalized["recommendation"] = normalized[key]
                break

    # Defaults for missing required fields
    normalized.setdefault("file", "unknown")
    normalized.setdefault("title", "Potential issue")
    normalized.setdefault(
        "description",
        str(normalized.get("title") or "Model reported an issue without details."),
    )
    normalized.setdefault(
        "recommendation",
        "Review this finding manually and apply an appropriate fix.",
    )
    normalized.setdefault("severity", "medium")
    normalized.setdefault("category", "other")

    # Line may arrive as string / float / "n/a"
    line = normalized.get("line")
    if isinstance(line, str):
        digits = re.search(r"\d+", line)
        normalized["line"] = int(digits.group()) if digits else None
    elif isinstance(line, float):
        normalized["line"] = int(line)
    elif line is not None and not isinstance(line, int):
        normalized["line"] = None

    try:
        return ReviewIssue.model_validate(normalized).model_dump()
    except ValidationError:
        # Last-resort defaults for enum drift.
        try:
            return ReviewIssue.model_validate(
                {
                    "file": str(normalized.get("file") or "unknown")[:1024],
                    "line": normalized.get("line")
                    if isinstance(normalized.get("line"), int)
                    else None,
                    "severity": "medium",
                    "category": "other",
                    "title": str(normalized.get("title") or "Potential issue")[:256],
                    "description": str(
                        normalized.get("description") or "Unstructured finding."
                    )[:4000],
                    "recommendation": str(
                        normalized.get("recommendation")
                        or "Review manually and fix if needed."
                    )[:4000],
                }
            ).model_dump()
        except ValidationError:
            return None


def parse_chunk_review(text: str) -> ChunkReviewResult | None:
    """Parse and validate a chunk-level review response."""
    data = extract_json_object(text)
    if data is None:
        logger.warning(
            "LLM response did not contain a JSON object: %s",
            (text or "")[:240].replace("\n", " "),
        )
        return None

    # Normalize common shape drift.
    if "issues" not in data:
        for key in ("findings", "problems", "results", "items"):
            if isinstance(data.get(key), list):
                data["issues"] = data[key]
                break
    if "issues" not in data and any(
        k in data for k in ("title", "file", "severity", "description")
    ):
        # Model returned a single issue object.
        data = {"overall_score": None, "summary": None, "issues": [data]}

    if "issues" not in data:
        data["issues"] = []

    raw_issues = data.get("issues")
    salvaged: list[dict[str, Any]] = []
    if isinstance(raw_issues, list):
        for item in raw_issues:
            if isinstance(item, dict):
                coerced = _coerce_issue(item)
                if coerced is not None:
                    salvaged.append(coerced)
            elif isinstance(item, str) and item.strip():
                coerced = _coerce_issue(
                    {
                        "title": item.strip()[:256],
                        "description": item.strip(),
                    }
                )
                if coerced is not None:
                    salvaged.append(coerced)

    summary = data.get("summary")
    if summary is not None and not isinstance(summary, str):
        summary = str(summary)

    try:
        return ChunkReviewResult.model_validate(
            {
                "overall_score": _coerce_score(data.get("overall_score")),
                "summary": summary,
                "issues": salvaged,
            }
        )
    except ValidationError as exc:
        logger.warning("LLM JSON failed schema validation after coercion: %s", exc)
        return ChunkReviewResult(
            overall_score=_coerce_score(data.get("overall_score")),
            summary=summary if isinstance(summary, str) else None,
            issues=[],
        )
