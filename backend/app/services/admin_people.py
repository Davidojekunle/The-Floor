"""Admins (staff) and the admin change log.

Only the owner (OWNER_EMAIL) can make or remove admins. Every change to a site switch and every admin
added or removed is written to admin_events, so the admin page can show who did what and when.
"""
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import Conflict, NotFound
from app.models.admin_event import AdminEvent
from app.models.user import User
from app.utils.time import as_utc, utcnow


def owner_emails() -> set[str]:
    return {e.strip().lower() for e in get_settings().owner_email.split(",") if e.strip()}


def is_owner(user: User | None) -> bool:
    return user is not None and user.email.lower() in owner_emails()


def require_owner(user: User) -> None:
    if not is_owner(user):
        raise NotFound("Not found.")  # don't advertise it


def log(db: Session, actor: User, action: str, detail: dict) -> None:
    """Add a log row (committed with the caller's change)."""
    db.add(AdminEvent(created_at=utcnow(), actor_id=actor.id, actor_name=actor.name[:100], action=action, detail=detail))


def list_admins(db: Session) -> list[dict]:
    staff = db.scalars(select(User).where(User.is_staff.is_(True)).order_by(User.name)).all()
    return [{"id": u.id, "name": u.name, "email": u.email, "is_owner": is_owner(u)} for u in staff]


def add_admin(db: Session, owner: User, email: str) -> list[dict]:
    require_owner(owner)
    user = db.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))
    if user is None:
        raise NotFound("No account uses that email. They need to sign up first.")
    if not user.is_staff:
        user.is_staff = True
        log(db, owner, "admin_added", {"name": user.name, "email": user.email})
        db.commit()
    return list_admins(db)


def remove_admin(db: Session, owner: User, user_id: uuid.UUID) -> list[dict]:
    require_owner(owner)
    user = db.get(User, user_id)
    if user is None or not user.is_staff:
        raise NotFound("That person isn't an admin.")
    if is_owner(user):
        raise Conflict("The owner stays an admin.")
    user.is_staff = False
    log(db, owner, "admin_removed", {"name": user.name, "email": user.email})
    db.commit()
    return list_admins(db)


def events(db: Session, limit: int = 50) -> list[dict]:
    rows = db.scalars(select(AdminEvent).order_by(AdminEvent.created_at.desc()).limit(limit)).all()
    return [
        {"id": r.id, "created_at": as_utc(r.created_at), "actor_name": r.actor_name, "action": r.action, "detail": r.detail or {}}
        for r in rows
    ]
