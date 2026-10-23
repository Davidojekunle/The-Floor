import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.openapi import ME_RESPONSES, MY_TASKS_RESPONSES
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import MeResponse, UpdateMeRequest
from app.schemas.common import PageParams, UtcDateTime, page_params_tasks
from app.schemas.task import MyTaskPage
from app.services import account_service, my_task_service, notification_service, room_service

router = APIRouter()


def build_me(db: Session, user: User) -> MeResponse:
    return MeResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        timezone=user.timezone,
        theme=user.theme,
        pending_email=account_service.pending_email(db, user),
        unread_notifications=notification_service.unread_count(db, user),
        rooms=room_service.list_rooms_for_user(db, user),
        is_staff=user.is_staff,
        email_verified=account_service.is_verified(user),
    )


@router.get("/me", response_model=MeResponse, responses=ME_RESPONSES)
def get_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return build_me(db, user)


@router.patch("/me", response_model=MeResponse, responses=ME_RESPONSES)
def update_me(body: UpdateMeRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Change any of name, timezone, theme. Other tabs and devices get `account_changed`."""
    account_service.update_profile(db, user, body.model_dump(exclude_unset=True))
    return build_me(db, user)


@router.get("/me/tasks", response_model=MyTaskPage, responses=MY_TASKS_RESPONSES)
def list_my_tasks(
    scope: Annotated[Literal["mine", "all"], Query(description="mine: tasks I'm part of. all: every task in my rooms")] = "mine",
    actionable: Annotated[bool | None, Query(description="Only tasks where one of MY stages is todo, in_progress, or blocked")] = None,
    from_: Annotated[UtcDateTime | None, Query(alias="from", description="Window start, inclusive")] = None,
    to: Annotated[UtcDateTime | None, Query(description="Window end, exclusive")] = None,
    status: Annotated[Literal["not_started", "in_progress", "done"] | None, Query()] = None,
    overdue: Annotated[bool | None, Query()] = None,
    blocked: Annotated[bool | None, Query(description="Only tasks with a blocked stage")] = None,
    room: Annotated[uuid.UUID | None, Query(description="Narrow to one of my rooms")] = None,
    approval_status: Annotated[
        str | None,
        Query(description="Comma-separated: approved (default), pending, rejected. Pending/rejected = my own proposals."),
    ] = None,
    sort: Annotated[Literal["due_date", "submitted_at"], Query()] = "due_date",
    params: PageParams = Depends(page_params_tasks),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items, total = my_task_service.list_my_tasks(
        db, user, params, scope=scope, actionable=actionable, from_=from_, to=to,
        status=status, overdue=overdue, blocked=blocked, room=room,
        approval_status=approval_status, sort=sort,
    )
    return MyTaskPage(items=items, total=total, page=params.page, limit=params.limit)
