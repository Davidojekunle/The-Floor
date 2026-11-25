import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class AssistantTurn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=2000)


class AssistantRequest(BaseModel):
    """Send the whole conversation each time, newest last; it must end with the person's turn.
    Leave conversation_id out to start a new description (this is what counts toward the weekly limit)."""

    conversation_id: uuid.UUID | None = None
    messages: list[AssistantTurn] = Field(min_length=1, max_length=12)

    @field_validator("messages")
    @classmethod
    def ends_with_person(cls, v: list[AssistantTurn]) -> list[AssistantTurn]:
        if v[-1].role != "user":
            raise ValueError("The last message must be yours.")
        if sum(len(m.text) for m in v) > 8000:
            raise ValueError("That's too long. Try a shorter description.")
        return v


class DraftStageOut(BaseModel):
    title: str
    assignee_id: uuid.UUID | None = None
    tag_id: uuid.UUID | None = None
    due_date: str | None = Field(None, description="YYYY-MM-DD in the person's time zone")
    parallel_with_previous: bool = False


class DraftTaskOut(BaseModel):
    title: str
    description: str | None = None
    due_date: str = Field(description="YYYY-MM-DD in the person's time zone")
    stages: list[DraftStageOut]


class AssistantReply(BaseModel):
    conversation_id: uuid.UUID
    kind: Literal["questions", "draft"] = Field(description="questions: answer them and send again. draft: confirm, then fill the form")
    message: str = Field(description="The questions, or a plain summary of the draft to confirm")
    questions: list[str] = []
    draft: DraftTaskOut | None = None
    turns_left: int
    uses_left: int = Field(description="New descriptions this room has left in the last 7 days")


class AssistantStatus(BaseModel):
    ready: bool = Field(description="The assistant is set up on this server")
    limit: int
    uses_left: int
