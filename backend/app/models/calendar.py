import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.utils.time import utcnow


class CalendarFeed(Base):
    """A private calendar subscription link. room_id null = the person's own work across rooms;
    set = everything in that room (still owned by one person, and dead once they leave it).
    The token is the whole secret: anyone with the link can read the feed, so it can be reset."""

    __tablename__ = "calendar_feeds"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    token: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    room_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
