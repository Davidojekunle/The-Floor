"""Forgotten password: email a single-use link; resetting signs out everywhere."""
import hashlib
import secrets
from datetime import timedelta

from fastapi import Request
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ResetTokenInvalid
from app.core.security import hash_password
from app.models.email import PasswordResetToken
from app.models.user import User
from app.services import email_service, session_service
from app.services.auth_service import normalize_email
from app.utils.time import as_utc, utcnow

ACCOUNT_LIMIT_PER_HOUR = 3


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def request_reset(db: Session, email: str, request: Request | None) -> None:
    """Always returns quietly: whether or not the account exists, the caller answers 202 the same way."""
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None:
        return
    now = utcnow()
    recent = db.scalar(
        select(func.count()).select_from(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id, PasswordResetToken.created_at > now - timedelta(hours=1)
        )
    )
    if recent >= ACCOUNT_LIMIT_PER_HOUR:
        return  # silent: still 202, nothing sent

    # a new link cancels any earlier one
    db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None),
               PasswordResetToken.cancelled_at.is_(None))
        .values(cancelled_at=now)
    )
    raw = secrets.token_urlsafe(32)
    minutes = get_settings().password_reset_minutes
    db.add(PasswordResetToken(user_id=user.id, token_hash=_hash(raw), created_at=now,
                              expires_at=now + timedelta(minutes=minutes)))
    link = f"{email_service.link_base(request)}/reset-password?token={raw}"
    text, html_body = email_service.render(
        "Reset your Taskroom password",
        [f"Hi {user.name},", f"Someone asked to reset the password for this account. The link works once and "
         f"expires in {minutes} minutes."],
        button=("Choose a new password", link),
        footer="If you didn't ask for this, ignore this email. Your password stays the same.",
    )
    email_service.queue(db, to=user.email, subject="Reset your Taskroom password", text=text, html_body=html_body,
                        category="security", user_id=user.id)
    db.commit()


def reset(db: Session, raw: str, new_password: str) -> None:
    token = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == _hash(raw)))
    now = utcnow()
    if (token is None or token.used_at is not None or token.cancelled_at is not None
            or as_utc(token.expires_at) <= now):
        raise ResetTokenInvalid("This link is invalid or has expired. Ask for a new one.")
    user = db.get(User, token.user_id)
    if user is None:
        raise ResetTokenInvalid("This link is invalid or has expired. Ask for a new one.")

    token.used_at = now
    user.password_hash = hash_password(new_password)
    session_service.sign_out_everywhere(db, user)  # including whoever had the old password
    text, html_body = email_service.render(
        "Your password was changed",
        [f"Hi {user.name},", "The password for your Taskroom account was just reset, and every device was signed out."],
        footer="If this wasn't you, reset your password again straight away.",
    )
    email_service.queue(db, to=user.email, subject="Your Taskroom password was changed", text=text,
                        html_body=html_body, category="security", user_id=user.id)
    db.commit()
