from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, InvalidCredentials
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
    message = "An account with this email already exists."
    taken = Conflict(message, fields={"email": message})

    if db.scalar(select(User).where(User.email == email)):
        raise taken
    db.commit()  # hand the database connection back while bcrypt runs: it takes seconds on a small CPU, and a
    # burst of sign-ins holding connections would run the pool dry

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
    db.commit()  # hand the database connection back while bcrypt runs: it takes seconds on a small CPU, and a
    # burst of sign-ins holding connections would run the pool dry
    if user is None:
        verify_password(password, _dummy_hash())
        raise InvalidCredentials("Incorrect email or password.")
    if not verify_password(password, user.password_hash):
        raise InvalidCredentials("Incorrect email or password.")
    return user
