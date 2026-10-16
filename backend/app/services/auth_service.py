from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Unauthenticated
from app.core.security import hash_password, verify_password
from app.models.user import User


def normalize_email(email: str) -> str:
    return email.strip().lower()


@lru_cache
def _dummy_hash() -> str:
    # Used so a login for an unknown email takes as long as a wrong password
    return hash_password("not-a-real-password")


def register_user(db: Session, *, name: str, email: str, password: str, timezone: str) -> User:
    email = normalize_email(email)
    taken = Conflict("An account with this email already exists.")

    if db.scalar(select(User).where(User.email == email)):
        raise taken

    user = User(name=name, email=email, password_hash=hash_password(password), timezone=timezone)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # two requests raced past the check above
        db.rollback()
        raise taken
    return user


def authenticate(db: Session, *, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None:
        verify_password(password, _dummy_hash())
        raise Unauthenticated("Incorrect email or password.")
    if not verify_password(password, user.password_hash):
        raise Unauthenticated("Incorrect email or password.")
    return user
