from datetime import timedelta

import bcrypt
import jwt

from app.core.config import get_settings
from app.core.errors import Unauthenticated
from app.utils.time import utcnow

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    rounds = get_settings().bcrypt_rounds
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def create_access_token(user_id) -> tuple[str, int]:
    """Returns (token, expires_in_seconds)."""
    settings = get_settings()
    expires_in = settings.access_token_expire_minutes * 60
    now = utcnow()
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM), expires_in


def decode_access_token(token: str) -> str:
    """Returns the user id (the `sub` claim) or raises Unauthenticated."""
    try:
        payload = jwt.decode(
            token,
            get_settings().secret_key,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError:
        raise Unauthenticated("Invalid or expired token.")
    return payload["sub"]


def decode_access_token_claims(token: str) -> dict:
    """Like decode_access_token, but returns all claims (the WebSocket needs `exp`)."""
    try:
        return jwt.decode(
            token,
            get_settings().secret_key,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError:
        raise Unauthenticated("Invalid or expired token.")


def token_predates_sign_out(claims: dict, user) -> bool:
    """True when the token was issued before the user's last sign-out-everywhere (inclusive: same second is fine)."""
    cutoff = getattr(user, "sessions_valid_after", None)
    if cutoff is None:
        return False
    if cutoff.tzinfo is None:  # SQLite hands back naive datetimes
        from datetime import timezone
        cutoff = cutoff.replace(tzinfo=timezone.utc)
    return int(claims.get("iat", 0)) < int(cutoff.timestamp())
