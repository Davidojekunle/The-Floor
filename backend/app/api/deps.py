import uuid

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import Unauthenticated
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User

# auto_error=False so we raise OUR 401 format instead of FastAPI's default
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise Unauthenticated("Not authenticated.")

    sub = decode_access_token(creds.credentials)
    try:
        user_id = uuid.UUID(sub)
    except ValueError:
        raise Unauthenticated("Invalid token.")

    user = db.get(User, user_id)
    if user is None:
        raise Unauthenticated("Account no longer exists.")
    return user


# Added in the next step:
#   get_room_context(room_id, user, db) -> loads the room + caller's membership,
#   and returns 404 if they aren't an active member.
