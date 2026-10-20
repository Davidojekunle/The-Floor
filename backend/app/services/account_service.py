"""L3: the account page. Profile and theme, change password, change email."""
import hashlib
import secrets
from datetime import timedelta

from fastapi import Request
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, EmailTokenInvalid, InvalidCredentials, ValidationFailed
from app.core.ratelimit import HOUR, limiter
from app.core.security import create_access_token, hash_password, verify_password
from app.models.email import EmailChangeToken
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.realtime import events as live
from app.services import email_service, session_service
from app.services.auth_service import normalize_email
from app.utils.time import as_utc, utcnow

EMAIL_CHANGE_HOURS = 24
PER_USER_PER_HOUR = 5
_BAD_LINK = "This link is invalid or has expired."


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _check_password(user: User, password: str) -> None:
    if not verify_password(password, user.password_hash):
        raise InvalidCredentials("Your current password is incorrect.", fields={"current_password": "Incorrect password."})


# ================================================================== profile

def update_profile(db: Session, user: User, changes: dict) -> User:
    """changes: only the fields the client sent (name, timezone, theme)."""
    changed = False
    for field in ("name", "timezone", "theme"):
        if field in changes and getattr(user, field) != changes[field]:
            setattr(user, field, changes[field])
            changed = True
    if changed:
        live.account_changed(db, user.id)
        db.commit()
    return user


# ================================================================== password

def _current_family(db: Session, user: User, refresh_raw: str | None):
    """The session (refresh family) of the browser making this request, if it has a live one."""
    if not refresh_raw:
        return None
    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == session_service._hash(refresh_raw)))
    if token is None or token.user_id != user.id or token.revoked_at is not None:
        return None
    return token.family_id


def change_password(db: Session, user: User, current: str, new: str, refresh_raw: str | None) -> tuple[str, int]:
    """Every other session ends at once. This browser keeps its refresh cookie and gets a fresh access token."""
    limiter.hit(f"change-password:{user.id}", PER_USER_PER_HOUR, HOUR)
    db.commit()  # hand the connection back during the three bcrypt runs below
    _check_password(user, current)
    if verify_password(new, user.password_hash):
        raise ValidationFailed("Choose a password you aren't using now.",
                               fields={"new_password": "Must be different from your current password."})

    user.password_hash = hash_password(new)
    session_service.sign_out_everywhere(db, user, keep_family=_current_family(db, user, refresh_raw))
    text, html_body = email_service.render(
        "Your password was changed",
        [f"Hi {user.name},", "The password for your account on The Floor was just changed. "
         "Every other device was signed out."],
        footer="If this wasn't you, reset your password straight away from the sign-in page.",
    )
    email_service.queue(db, to=user.email, subject="Your password for The Floor was changed", text=text,
                        html_body=html_body, category="security", user_id=user.id)
    db.commit()
    # issued after the cutoff (same second is fine: the check is inclusive), so this tab carries on
    return create_access_token(user.id)


# ================================================================== email

def _active_change(db: Session, user_id) -> EmailChangeToken | None:
    row = db.scalar(
        select(EmailChangeToken)
        .where(EmailChangeToken.user_id == user_id, EmailChangeToken.used_at.is_(None),
               EmailChangeToken.cancelled_at.is_(None))
        .order_by(EmailChangeToken.created_at.desc())
    )
    if row is None or as_utc(row.expires_at) <= utcnow():
        return None
    return row


def pending_email(db: Session, user: User) -> str | None:
    row = _active_change(db, user.id)
    return row.new_email if row else None


def _taken(db: Session, email: str, user: User) -> bool:
    return db.scalar(select(User.id).where(User.email == email, User.id != user.id)) is not None


def _taken_error() -> Conflict:
    message = "An account with this email already exists."
    return Conflict(message, fields={"new_email": message})


def _cancel_pending(db: Session, user_id) -> int:
    return db.execute(
        update(EmailChangeToken)
        .where(EmailChangeToken.user_id == user_id, EmailChangeToken.used_at.is_(None),
               EmailChangeToken.cancelled_at.is_(None))
        .values(cancelled_at=utcnow())
    ).rowcount


def request_email_change(db: Session, user: User, new_email: str, current: str, request: Request | None) -> None:
    limiter.hit(f"change-email:{user.id}", PER_USER_PER_HOUR, HOUR)
    _check_password(user, current)
    new_email = normalize_email(new_email)
    if new_email == user.email:
        raise ValidationFailed("That's already your email.", fields={"new_email": "That's already your email."})
    if _taken(db, new_email, user):
        raise _taken_error()

    _cancel_pending(db, user.id)  # a new request replaces the pending one
    raw, cancel_raw, now = secrets.token_urlsafe(32), secrets.token_urlsafe(32), utcnow()
    db.add(EmailChangeToken(user_id=user.id, new_email=new_email, token_hash=_hash(raw),
                            cancel_hash=_hash(cancel_raw), created_at=now,
                            expires_at=now + timedelta(hours=EMAIL_CHANGE_HOURS)))
    base = email_service.link_base(request)

    text, html_body = email_service.render(
        "Confirm your new email",
        [f"Hi {user.name},", f"Confirm that you want to use this address for The Floor. You'll need your "
         f"password. The link expires in {EMAIL_CHANGE_HOURS} hours."],
        button=("Confirm this email", f"{base}/confirm-email?token={raw}"),
        footer="If you didn't ask for this, ignore this email. Nothing changes without the account's password.",
    )
    email_service.queue(db, to=new_email, subject="Confirm your new email for The Floor", text=text,
                        html_body=html_body, category="security", user_id=user.id)

    text, html_body = email_service.render(
        "Your email is being changed",
        [f"Hi {user.name},", f"Someone signed in to your account on The Floor asked to change its email to {new_email}. "
         "Until that address is confirmed, nothing changes."],
        button=("This wasn't me, cancel it", f"{base}/cancel-email-change?token={cancel_raw}"),
        footer="If it wasn't you, cancel it and then reset your password, because someone else knows it.",
    )
    email_service.queue(db, to=user.email, subject="Your email for The Floor is being changed", text=text,
                        html_body=html_body, category="security", user_id=user.id)
    live.account_changed(db, user.id)
    db.commit()


def _usable(row: EmailChangeToken | None) -> bool:
    return (row is not None and row.used_at is None and row.cancelled_at is None
            and as_utc(row.expires_at) > utcnow())


def confirm_email(db: Session, raw: str, current: str) -> None:
    """Needs the password too, so whoever merely receives the link (say, at a mistyped address) can't take the account."""
    row = db.scalar(select(EmailChangeToken).where(EmailChangeToken.token_hash == _hash(raw)))
    if not _usable(row):
        raise EmailTokenInvalid(_BAD_LINK)
    user = db.get(User, row.user_id)
    if user is None:
        raise EmailTokenInvalid(_BAD_LINK)
    limiter.hit(f"confirm-email:{user.id}", PER_USER_PER_HOUR, HOUR)
    _check_password(user, current)
    if _taken(db, row.new_email, user):
        raise _taken_error()

    old = user.email
    user.email = row.new_email
    row.used_at = utcnow()
    text, html_body = email_service.render(
        "Your email was changed",
        [f"Hi {user.name},", f"Your account on The Floor now uses {row.new_email}. "
         "Sign in with that address from now on. This address won't get emails from The Floor any more."],
        footer="If you didn't make this change, someone else knows your password.",
    )
    email_service.queue(db, to=old, subject="Your email for The Floor was changed", text=text,
                        html_body=html_body, category="security", user_id=user.id)
    live.account_changed(db, user.id)
    try:
        db.commit()
    except IntegrityError:  # someone registered the address a moment ago
        db.rollback()
        raise _taken_error()


def cancel_email_change(db: Session, user: User) -> None:
    """From the account page. Safe to repeat."""
    if _cancel_pending(db, user.id):
        live.account_changed(db, user.id)
    db.commit()


def cancel_email_change_by_link(db: Session, raw: str) -> None:
    """The "this wasn't me" link sent to the old address. No login needed."""
    row = db.scalar(select(EmailChangeToken).where(EmailChangeToken.cancel_hash == _hash(raw)))
    if not _usable(row):
        raise EmailTokenInvalid(_BAD_LINK)
    row.cancelled_at = utcnow()
    live.account_changed(db, row.user_id)
    db.commit()
