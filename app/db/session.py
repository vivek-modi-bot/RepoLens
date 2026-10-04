"""Async SQLAlchemy engine and session management."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for ORM models."""


settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    connect_args={"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Create database tables and apply lightweight SQLite upgrades."""
    from sqlalchemy import text

    from app.models import (  # noqa: F401
        chunk_cache,
        finding_fix,
        review,
        review_message,
        user,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if settings.database_url.startswith("sqlite"):
            # Older local DBs may predate per-finding chat.
            cols = (
                await conn.execute(text("PRAGMA table_info(review_messages)"))
            ).fetchall()
            col_names = {row[1] for row in cols}
            if cols and "issue_index" not in col_names:
                await conn.execute(
                    text(
                        "ALTER TABLE review_messages "
                        "ADD COLUMN issue_index INTEGER NOT NULL DEFAULT 0"
                    )
                )

            user_cols = (
                await conn.execute(text("PRAGMA table_info(users)"))
            ).fetchall()
            user_col_names = {row[1] for row in user_cols}
            if user_cols and "github_token_encrypted" not in user_col_names:
                await conn.execute(
                    text(
                        "ALTER TABLE users "
                        "ADD COLUMN github_token_encrypted TEXT"
                    )
                )
