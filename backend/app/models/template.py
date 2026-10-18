import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.utils.time import utcnow


class TaskTemplate(Base):
    """A reusable list of stages, e.g. 'Video shoot': Script -> Shoot -> Edit."""

    __tablename__ = "task_templates"
    __table_args__ = (Index("uq_task_templates_room_name_lower", "room_id", func.lower(text("name")), unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TemplateStage(Base):
    __tablename__ = "template_stages"
    __table_args__ = (Index("ix_template_stages_template_position", "template_id", "position"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task_templates.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(120))
    tag_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tags.id", ondelete="SET NULL"), nullable=True, index=True
    )
    parallel_with_previous: Mapped[bool] = mapped_column(Boolean, default=False)
