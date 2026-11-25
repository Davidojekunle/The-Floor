import uuid

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import UtcDateTime


class DmUser(BaseModel):
    id: uuid.UUID
    name: str


class DmStart(BaseModel):
    user_id: uuid.UUID


class DmSend(BaseModel):
    body: str = Field(min_length=1, max_length=4000)

    @field_validator("body")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Write something first.")
        return v


class DmMessageOut(BaseModel):
    id: uuid.UUID
    sender_id: uuid.UUID
    body: str | None = Field(description="null once deleted")
    deleted: bool
    created_at: UtcDateTime


class DmThreadOut(BaseModel):
    id: uuid.UUID
    other: DmUser
    last_message: DmMessageOut | None = None
    last_message_at: UtcDateTime | None = None
    unread: int = 0
    you_blocked: bool = Field(description="You blocked them: nobody can send here until you unblock")
    can_send: bool = Field(description="False when either of you has blocked the other")


class DmThreadList(BaseModel):
    items: list[DmThreadOut]


class DmMessagePage(BaseModel):
    items: list[DmMessageOut] = Field(description="Oldest first")
    has_more: bool = Field(description="Older messages exist: ask again with before = the first item's created_at")
