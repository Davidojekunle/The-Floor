import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.utils.time import utcnow


class Tag(Base):
    """A role label inside ONE room (e.g. Video Editor). Same name in two rooms = two separate tags."""

    __tablename__ = "tags"
    __table_args__ = (
        # names are unique per room, ignoring case ("Editor" and "editor" clash)
        Index("uq_tags_room_name_lower", "room_id", func.lower(text("name")), unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MembershipTag(Base):
    """Which tags a member holds in a room. A member can hold several."""

    __tablename__ = "membership_tags"

    membership_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memberships.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)
