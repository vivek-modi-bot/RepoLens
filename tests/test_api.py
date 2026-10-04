"""API-level tests for health and review endpoints."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.github.processor import FetchedRepository
from app.github.validator import ParsedGitHubURL
from app.llm.base import LLMProvider
from app.schemas.review import ReviewResponse, ReviewStatistics
from app.services.review_service import ReviewService


class FakeLLM(LLMProvider):
    async def generate_review(self, prompt: str) -> str:
        return """
        {
          "overall_score": 88,
          "summary": "Solid codebase with minor issues.",
          "issues": [
            {
              "file": "app.py",
              "line": 3,
              "severity": "low",
              "category": "quality",
              "title": "Missing docstring",
              "description": "Public function lacks documentation.",
              "recommendation": "Add a concise docstring."
            }
          ]
        }
        """

    async def generate_text(self, prompt: str) -> str:
        return "Based on the findings, add a docstring to app.py."

    async def health_check(self) -> bool:
        return True


class FakeGitHubClient:
    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        pass

    async def __aenter__(self) -> FakeGitHubClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def resolve_branch_and_sha(
        self, parsed: ParsedGitHubURL, branch: str | None
    ) -> tuple[str, str]:
        return branch or "main", "abc123deadbeef"


def _patch_review_deps(
    monkeypatch: pytest.MonkeyPatch,
    fetched: FetchedRepository,
) -> None:
    async def fake_fetch(self, url, branch=None):  # noqa: ANN001
        return fetched

    monkeypatch.setattr(
        "app.services.repository_service.RepositoryService.fetch_repository",
        fake_fetch,
    )
    monkeypatch.setattr(
        "app.services.review_service.build_llm_provider",
        lambda settings: FakeLLM(),
    )
    monkeypatch.setattr(
        "app.services.review_service.GitHubClient",
        FakeGitHubClient,
    )


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_health(self):  # noqa: ANN001
        return True

    monkeypatch.setattr(
        "app.llm.ollama.OllamaProvider.health_check",
        fake_health,
    )
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "RepoLens"
    assert "llm_available" in body


@pytest.mark.asyncio
async def test_review_requires_auth(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/repository/review",
        json={
            "repository_url": "https://github.com/owner/repo",
            "branch": "main",
            "review_type": "full",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_review_invalid_url(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/api/v1/repository/review",
        headers=auth_headers,
        json={
            "repository_url": "https://gitlab.com/owner/repo",
            "review_type": "full",
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_review_endpoint_success(
    client: AsyncClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    fetched = FetchedRepository(
        owner="owner",
        repo="repo",
        branch="main",
        root_path=source,
        temp_dir=tmp_path,
        size_bytes=100,
    )
    fetched.cleanup = MagicMock()  # type: ignore[method-assign]
    _patch_review_deps(monkeypatch, fetched)

    response = await client.post(
        "/api/v1/repository/review",
        headers=auth_headers,
        json={
            "repository_url": "https://github.com/owner/repo",
            "branch": "main",
            "review_type": "quality",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["repository"] == "owner/repo"
    assert body["branch"] == "main"
    assert body["review_type"] == "quality"
    assert "overall_score" in body
    assert "issues" in body
    assert body["statistics"]["files_analyzed"] >= 1
    assert body["review_id"] is not None
    assert body["from_cache"] is False

    review_id = body["review_id"]
    get_response = await client.get(
        f"/api/v1/repository/{review_id}",
        headers=auth_headers,
    )
    assert get_response.status_code == 200
    assert get_response.json()["review_id"] == review_id

    # Second call should hit saved review cache.
    cached = await client.post(
        "/api/v1/repository/review",
        headers=auth_headers,
        json={
            "repository_url": "https://github.com/owner/repo",
            "branch": "main",
            "review_type": "quality",
        },
    )
    assert cached.status_code == 200
    assert cached.json()["from_cache"] is True
    assert cached.json()["review_id"] == review_id

    history = await client.get("/api/v1/repository/reviews", headers=auth_headers)
    assert history.status_code == 200
    assert any(item["review_id"] == review_id for item in history.json())

    ask = await client.post(
        f"/api/v1/repository/{review_id}/ask",
        headers=auth_headers,
        json={"question": "How should I fix this finding?", "issue_index": 0},
    )
    assert ask.status_code == 200
    ask_body = ask.json()
    assert ask_body["issue_index"] == 0
    assert "docstring" in ask_body["answer"].lower() or "app.py" in ask_body["answer"]
    assert len(ask_body["messages"]) >= 2

    messages = await client.get(
        f"/api/v1/repository/{review_id}/messages?issue_index=0",
        headers=auth_headers,
    )
    assert messages.status_code == 200
    assert len(messages.json()) >= 2

    missing = await client.post(
        f"/api/v1/repository/{review_id}/ask",
        headers=auth_headers,
        json={"question": "What about this?", "issue_index": 99},
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_get_review_not_found(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.get(
        f"/api/v1/repository/{uuid4()}",
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_review_service_persists(
    db_session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.security import hash_password
    from app.models.user import User
    from app.schemas.repository import RepositoryReviewRequest

    user = User(username="svcuser", hashed_password=hash_password("password12345"))
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    source = tmp_path / "src"
    source.mkdir()
    (source / "main.py").write_text("print('ok')\n", encoding="utf-8")
    fetched = FetchedRepository(
        owner="acme",
        repo="demo",
        branch="main",
        root_path=source,
        temp_dir=tmp_path,
        size_bytes=20,
    )
    fetched.cleanup = MagicMock()  # type: ignore[method-assign]

    repo_service = MagicMock()
    repo_service.fetch_repository = AsyncMock(return_value=fetched)
    monkeypatch.setattr(
        "app.services.review_service.GitHubClient",
        FakeGitHubClient,
    )

    service = ReviewService(
        db=db_session,
        repository_service=repo_service,
        llm_provider=FakeLLM(),
    )
    result = await service.review_repository(
        RepositoryReviewRequest(
            repository_url="https://github.com/acme/demo",
            branch="main",
            review_type="full",
        ),
        user,
    )
    assert isinstance(result, ReviewResponse)
    assert result.review_id is not None
    assert isinstance(result.statistics, ReviewStatistics)

    # Chunks should be reused on force refresh with same commit.
    result2 = await service.review_repository(
        RepositoryReviewRequest(
            repository_url="https://github.com/acme/demo",
            branch="main",
            review_type="security",
            force_refresh=True,
        ),
        user,
    )
    assert result2.chunks_reused is True
    assert repo_service.fetch_repository.await_count == 1
