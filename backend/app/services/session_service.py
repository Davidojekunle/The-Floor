"""Refresh tokens: issue on login, rotate on refresh, end on logout or theft."""
import hashlib
import secrets
import uuid
from datetime import timedelta

from sqlalchemy import exists, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import Unauthenticated
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.utils.time import as_utc, utcnow

# why a token was revoked
LOGOUT, THEFT, SUPERSEDED, ALL_SESSIONS = "logout", "theft", "superseded", "logout_all"


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _issue(db: Session, *, user_id, family_id, parent_id=None) -> str:
    raw = secrets.token_urlsafe(48)
    now = utcnow()
    db.add(
        RefreshToken(
            user_id=user_id,
            family_id=family_id,
            parent_id=parent_id,
            token_hash=_hash(raw),
            created_at=now,
            expires_at=now + timedelta(days=get_settings().refresh_token_days),
        )
    )
    return raw


def _end_family(db: Session, family_id, reason: str) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow(), revoke_reason=reason)
    )


def start_session(db: Session, user: User) -> str:
    """On login: a new family with its first token. The caller commits."""
    return _issue(db, user_id=user.id, family_id=uuid.uuid4())


class SessionEnded(Unauthenticated):
    """401 that also tells the route to clear the cookie."""


def rotate(db: Session, raw: str | None) -> tuple[User, str]:
    """Returns (user, new raw refresh token). Raises SessionEnded (after committing any revocation)."""
    if not raw:
        raise SessionEnded("Not signed in.")
    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == _hash(raw)))
    now = utcnow()

    if token is None:
        raise SessionEnded("Your session has ended. Please sign in again.")

    if token.revoked_at is not None:
        if token.revoke_reason == SUPERSEDED:
            # a cancelled replacement: the real browser never received it, so this is a stolen copy
            _end_family(db, token.family_id, THEFT)
            db.commit()
        raise SessionEnded("Your session has ended. Please sign in again.")

    if as_utc(token.expires_at) <= now:
        raise SessionEnded("Your session has expired. Please sign in again.")

    user = db.get(User, token.user_id)
    if user is None:
        raise SessionEnded("Account no longer exists.")

    from app.core.ratelimit import MINUTE, limiter
    limiter.hit(f"refresh:session:{token.family_id}", 60, MINUTE)  # every page load and new tab renews once

    if token.used_at is None:
        token.used_at = now  # the normal case: first and only use
    else:
        grace = timedelta(seconds=get_settings().refresh_reuse_grace_seconds)
        if now - as_utc(token.used_at) > grace:
            replacement_used = db.scalar(
                select(exists().where(RefreshToken.parent_id == token.id, RefreshToken.used_at.is_not(None)))
            )
            if replacement_used:
                # two different holders have both used this chain: end the whole session
                _end_family(db, token.family_id, THEFT)
                db.commit()
                raise SessionEnded("Your session has ended. Please sign in again.")
            # a lost response: cancel the unused replacement(s) so only one live branch remains
            db.execute(
                update(RefreshToken)
                .where(RefreshToken.parent_id == token.id, RefreshToken.revoked_at.is_(None))
                .values(revoked_at=now, revoke_reason=SUPERSEDED)
            )
        # within the grace period: another tab refreshing at the same moment, just issue another

    new_raw = _issue(db, user_id=user.id, family_id=token.family_id, parent_id=token.id)
    db.commit()
    return user, new_raw


def end_session(db: Session, raw: str | None) -> None:
    """Logout. Safe to repeat, even without a token."""
    if not raw:
        return
    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == _hash(raw)))
    if token is not None:
        _end_family(db, token.family_id, LOGOUT)
        db.commit()


def end_all_sessions(db: Session, user: User) -> None:
    sign_out_everywhere(db, user)
    db.commit()


def sign_out_everywhere(db: Session, user: User, keep_family=None) -> None:
    """Ends every session at once: refresh tokens, live access tokens, and open sockets. The caller commits.

    keep_family: one session (this browser) that may keep refreshing, e.g. after a password change.
    """
    from app.realtime import events as live

    q = update(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
    if keep_family is not None:
        q = q.where(RefreshToken.family_id != keep_family)
    db.execute(q.values(revoked_at=utcnow(), revoke_reason=ALL_SESSIONS))
    user.sessions_valid_after = utcnow().replace(microsecond=0)
    live.close_sockets(db, user.id)
    from app.services import push_service

    push_service.forget_all(db, user.id)
