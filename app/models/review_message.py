"""Persisted Q&A messages about a specific review finding."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ReviewMessage(Base):
    __tablename__ = "review_messages"

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
    issue_index: Mapped[int] = mapped_column(Integer, index=True, default=0)
    role: Mapped[str] = mapped_column(String(32))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
