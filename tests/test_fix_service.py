"""Tests for fix suggestion parsing and PR guards."""

from __future__ import annotations

import pytest

from app.core.exceptions import LLMResponseError
from app.services.fix_service import FixService


def test_parse_fix_response_accepts_valid_json() -> None:
    service = FixService(db=None)  # type: ignore[arg-type]
    raw = """
    {
      "file": "app.py",
      "explanation": "Add a docstring",
      "commit_message": "docs: add docstring",
      "updated_content": "def add(a, b):\\n    \\"\\"\\"Add.\\"\\"\\"\\n    return a + b\\n"
    }
    """
    parsed = service._parse_fix_response(raw, fallback_path="app.py")
    assert parsed["file_path"] == "app.py"
    assert "Add a docstring" in parsed["explanation"]
    assert "def add" in parsed["updated_content"]


def test_parse_fix_response_accepts_fenced_format() -> None:
    service = FixService(db=None)  # type: ignore[arg-type]
    raw = """
EXPLANATION: Add a guard clause
COMMIT: fix: handle empty input
```python
def run(value):
    if not value:
        return None
    return value.strip()
```
"""
    parsed = service._parse_fix_response(raw, fallback_path="main.py")
    assert "guard" in parsed["explanation"].lower()
    assert parsed["commit_message"].startswith("fix:")
    assert "if not value" in parsed["updated_content"]


def test_parse_fix_response_salvages_broken_json_string() -> None:
    service = FixService(db=None)  # type: ignore[arg-type]
    raw = (
        '{"file":"a.py","explanation":"Improve naming","commit_message":"refactor: rename",'
        '"updated_content":"print(\\"hi\\")\\n"'
    )
    parsed = service._parse_fix_response(raw, fallback_path="a.py")
    assert "print" in parsed["updated_content"]


def test_parse_fix_response_rejects_missing_content() -> None:
    service = FixService(db=None)  # type: ignore[arg-type]
    with pytest.raises(LLMResponseError):
        service._parse_fix_response("sorry I cannot help", fallback_path="a.py")
