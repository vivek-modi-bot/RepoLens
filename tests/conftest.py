"""Shared pytest fixtures."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Configure test environment before importing the app.
os.environ["JWT_SECRET_KEY"] = "test-secret-key-which-is-long-enough"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["OLLAMA_BASE_URL"] = "http://ollama-test:11434"
os.environ["LLM_PROVIDER"] = "ollama"
os.environ["DEBUG"] = "true"
os.environ["TEMP_DIR"] = "/tmp/repolens-test"

from app.core.config import get_settings
from app.db.session import Base, get_db
from app.main import create_app
from app.models import Review, User  # noqa: F401

get_settings.cache_clear()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    app = create_app()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    register = await client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "password": "securepass123", "email": "a@example.com"},
    )
    assert register.status_code == 201

    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "securepass123"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
