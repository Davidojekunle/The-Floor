import uuid
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.room import RoomSummary


Theme = Literal["system", "light", "dark"]


def check_name(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("Name can't be empty.")
    return v


def check_timezone(v: str) -> str:
    try:
        ZoneInfo(v)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("Unknown timezone.")
    return v


def check_password_bytes(v: str) -> str:
    # bcrypt only uses the first 72 bytes, so reject longer ones instead of silently truncating
    if len(v.encode()) > 72:
        raise ValueError("Password must be at most 72 bytes.")
    return v


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8)
    timezone: str = "UTC"

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return check_name(v)

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, v: str) -> str:
        return check_password_bytes(v)

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, v: str) -> str:
        return check_timezone(v)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    timezone: str
    theme: Theme = "system"


class MeResponse(UserOut):
    pending_email: str | None = Field(None, description="Set while an email change waits for confirmation. Login still uses `email`.")
    unread_notifications: int = 0
    rooms: list[RoomSummary] = []


class UpdateMeRequest(BaseModel):
    """Send only what changes. Omit a field to leave it as it is (null isn't allowed)."""

    name: str | None = Field(None, min_length=1, max_length=100)
    timezone: str | None = None
    theme: Theme | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, v):
        if v is None:
            raise ValueError("Name can't be null. Leave it out to keep it.")
        return check_name(v)

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, v):
        if v is None:
            raise ValueError("Timezone can't be null. Leave it out to keep it.")
        return check_timezone(v)

    @field_validator("theme", mode="before")
    @classmethod
    def theme_not_null(cls, v):
        if v is None:
            raise ValueError("Theme can't be null. Leave it out to keep it.")
        return v


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8)

    @field_validator("new_password")
    @classmethod
    def fits_bcrypt(cls, v: str) -> str:
        return check_password_bytes(v)


class ChangeEmailRequest(BaseModel):
    new_email: EmailStr
    current_password: str = Field(min_length=1)


class ConfirmEmailRequest(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    current_password: str = Field(min_length=1)


class CancelEmailChangeRequest(BaseModel):
    token: str = Field(min_length=1, max_length=200)


class RefreshResponse(TokenResponse):
    """A new access token, plus the GET /me body so page load needs one call."""

    me: MeResponse


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8)

    @field_validator("new_password")
    @classmethod
    def fits_bcrypt(cls, v: str) -> str:
        return check_password_bytes(v)


class AcceptedResponse(BaseModel):
    message: str
