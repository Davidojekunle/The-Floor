import uuid

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import Page, UtcDateTime
from app.schemas.member import TagBrief


def _clean(v: str | None, what: str) -> str | None:
    if v is None:
        return v
    v = " ".join(v.split())
    if not v:
        raise ValueError(f"{what} can't be empty.")
    return v


# ------------------------------------------------------------------ input

class TemplateStageIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    tag_id: uuid.UUID | None = None
    parallel_with_previous: bool = False

    @field_validator("title")
    @classmethod
    def clean_title(cls, v: str) -> str:
        return _clean(v, "Title")


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    stages: list[TemplateStageIn] = Field(min_length=1, max_length=30)

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        return _clean(v, "Name")


class TemplateUpdate(BaseModel):
    """Send name and/or stages. stages REPLACES the whole list."""

    name: str | None = Field(None, min_length=1, max_length=100)
    stages: list[TemplateStageIn] | None = Field(None, min_length=1, max_length=30)

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str | None) -> str | None:
        return _clean(v, "Name")


class TemplateApply(BaseModel):
    """Creates a task from the template. Stages copy title, tag and parallel flag; no assignees or stage dates."""

    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(None, max_length=5000)
    start_date: UtcDateTime | None = None
    due_date: UtcDateTime

    @field_validator("title")
    @classmethod
    def clean_title(cls, v: str) -> str:
        return _clean(v, "Title")


# ------------------------------------------------------------------ output

class TemplateStageOut(BaseModel):
    position: int
    title: str
    tag: TagBrief | None
    parallel_with_previous: bool


class TemplateOut(BaseModel):
    id: uuid.UUID
    name: str
    stages: list[TemplateStageOut]


class TemplatePage(Page[TemplateOut]):
    pass
