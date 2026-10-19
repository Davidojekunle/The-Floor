import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.utils.time import utcnow


class Notification(Base):
    """One bell item. Names are copied in when it's created, so it still reads right after a
    room, task or stage is renamed or deleted (those ids are plain columns, not foreign keys)."""

    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_created", "user_id", "created_at"),
        Index("ix_notifications_email_due", "email_due_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(40))
    category: Mapped[str] = mapped_column(String(20))  # requests | decisions | assignments
    title: Mapped[str] = mapped_column(String(400))
    room_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    room_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    task_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    stage_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    stage_title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    actor_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # email: due = when its group goes out (null = no email); emailed_at = done (sent or skipped)
    email_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    emailed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NotificationSettings(Base):
    """Absent row = every switch on."""

    __tablename__ = "notification_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    requests: Mapped[bool] = mapped_column(Boolean, default=True)
    decisions: Mapped[bool] = mapped_column(Boolean, default=True)
    assignments: Mapped[bool] = mapped_column(Boolean, default=True)
    daily_digest: Mapped[bool] = mapped_column(Boolean, default=True)
    mentions: Mapped[bool] = mapped_column(Boolean, default=True)  # someone @mentions you in chat
    all_messages: Mapped[bool] = mapped_column(Boolean, default=False)  # push for every chat message (push only)
    last_digest_on: Mapped[date | None] = mapped_column(Date, nullable=True)  # the user's local date


class MutedRoom(Base):
    __tablename__ = "muted_rooms"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
