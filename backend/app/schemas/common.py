from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated, Generic, TypeVar

from fastapi import Query
from pydantic import AfterValidator, BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    limit: int


@dataclass
class PageParams:
    page: int
    limit: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


def page_params(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100)) -> PageParams:
    return PageParams(page=page, limit=limit)


def page_params_large(page: int = Query(1, ge=1), limit: int = Query(100, ge=1, le=100)) -> PageParams:
    """For short lists that feed dropdowns (e.g. tags), so the default page holds everything."""
    return PageParams(page=page, limit=limit)


def page_params_tasks(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=500)) -> PageParams:
    """Tasks allow up to 500 per page so a calendar window can load everything in one call."""
    return PageParams(page=page, limit=limit)


def _require_timezone(v: datetime) -> datetime:
    if v.tzinfo is None:
        raise ValueError("Use an ISO date with a timezone, for example 2026-10-30T17:00:00Z.")
    return v.astimezone(timezone.utc)


# A datetime that must carry a timezone and is normalised to UTC
UtcDateTime = Annotated[datetime, AfterValidator(_require_timezone)]
