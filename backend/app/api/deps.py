import uuid

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import NotFound, Unauthenticated
from app.core.ratelimit import MINUTE, limiter
from app.core.security import decode_access_token_claims, token_predates_sign_out
from app.db.session import get_db
from app.models.user import User
from app.permissions.rules import RoomContext
from app.services import room_service

# auto_error=False so we raise OUR 401 format instead of FastAPI's default
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise Unauthenticated("Not authenticated.")

    claims = decode_access_token_claims(creds.credentials)
    try:
        user_id = uuid.UUID(claims["sub"])
    except ValueError:
        raise Unauthenticated("Invalid token.")

    user = db.get(User, user_id)
    if user is None:
        raise Unauthenticated("Account no longer exists.")
    if token_predates_sign_out(claims, user):
        raise Unauthenticated("You were signed out. Please sign in again.")
    limiter.hit(f"user:{user.id}", 300, MINUTE)  # a safety net normal use never reaches
    return user


def require_staff(user: User = Depends(get_current_user)) -> User:
    """Staff only. Everyone else gets a plain 404, so the admin routes don't advertise themselves."""
    if not user.is_staff:
        raise NotFound("Not found.")
    return user


def get_room_context(
    room_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RoomContext:
    """Use on EVERY /rooms/{room_id}/... route. 404 unless the caller is an active member."""
    return room_service.get_room_context(db, room_id, user)
