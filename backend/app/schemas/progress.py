import uuid
from datetime import datetime
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

from app.schemas.message import Ref
from app.schemas.room import UserBrief


class UpdateCreate(BaseModel):
    note: str = Field(min_length=1, max_length=2000)
    link_url: str | None = Field(None, max_length=2000)
    share_to_chat: bool = False

    @field_validator("note")
    @classmethod
    def strip_note(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Note can't be empty.")
        return v

    @field_validator("link_url")
    @classmethod
    def web_link_only(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        v = v.strip()
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("Use a web link starting with http:// or https://.")
        return v


class UpdateOut(BaseModel):
    id: uuid.UUID
    stage: Ref
    author: UserBrief
    note: str
    link_url: str | None
    created_at: datetime
    can_delete: bool


class UpdatePage(BaseModel):
    items: list[UpdateOut]
    has_more: bool
