import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import Page, UtcDateTime
from app.schemas.room import RoleName, UserBrief


class TagBrief(BaseModel):
    id: uuid.UUID
    name: str


class TagOut(TagBrief):
    member_count: int = 0


def _clean_tag_name(v: str) -> str:
    v = " ".join(v.split())  # trim and collapse inner whitespace
    if not v:
        raise ValueError("Tag name can't be empty.")
    return v


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        return _clean_tag_name(v)


class TagUpdate(TagCreate):
    """Same rules as creating a tag."""


class MemberOut(BaseModel):
    membership_id: uuid.UUID
    user: UserBrief
    role: RoleName  # effective role: head, temp_head (active grant), or member
    temp_head_expires_at: datetime | None = None  # set while they're an active temp head
    status: Literal["active"] = "active"
    tags: list[TagBrief]
    joined_at: datetime | None = None


class MemberTagsUpdate(BaseModel):
    """Replaces the member's tags with exactly this set. Send [] to clear them."""

    tag_ids: list[uuid.UUID]


class TagPage(Page[TagOut]):
    pass


class MemberPage(Page[MemberOut]):
    pass


class TempHeadGrant(BaseModel):
    """Grant, extend, or shorten. Up to the end of the 90th day after today in the head's timezone."""

    expires_at: UtcDateTime
