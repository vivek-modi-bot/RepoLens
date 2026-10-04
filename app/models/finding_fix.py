"""Persisted AI-generated code fixes for review findings."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class FindingFix(Base):
    __tablename__ = "finding_fixes"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    review_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("reviews.id"),
        index=True,
    )
    issue_index: Mapped[int] = mapped_column(Integer, index=True)
    file_path: Mapped[str] = mapped_column(String(1024))
    original_content: Mapped[str] = mapped_column(Text)
    updated_content: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text, default="")
    commit_message: Mapped[str] = mapped_column(String(255), default="fix: apply RepoLens suggestion")
    pr_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
