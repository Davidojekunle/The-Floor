import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.utils.time import utcnow


class ProgressUpdate(Base):
    """A short note posted on a stage ("Shot 3 of 5 scenes"), with an optional link."""

    __tablename__ = "progress_updates"
    __table_args__ = (
        Index("ix_progress_updates_stage_created", "stage_id", "created_at", "id"),
        Index("ix_progress_updates_task_created", "task_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    stage_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stages.id", ondelete="CASCADE"))
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str] = mapped_column(Text)
    link_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
