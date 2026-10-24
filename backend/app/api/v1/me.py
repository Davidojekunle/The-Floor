import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.openapi import ME_RESPONSES, MY_TASKS_RESPONSES
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import MeResponse, UpdateMeRequest
from app.schemas.call import CallPage
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
        calls_enabled=get_settings().calls_enabled,
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


@router.get("/me/calls", response_model=CallPage, responses=ME_RESPONSES)
def list_my_calls(
    from_: Annotated[UtcDateTime | None, Query(alias="from", description="Default: now")] = None,
    to: Annotated[UtcDateTime | None, Query(description="Default: 60 days after `from`")] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """My calendar: meetings I'm invited to in the window, and calls live now, across my rooms."""
    if not get_settings().calls_enabled:
        from app.core.errors import NotFound

        raise NotFound("Not found.")
    from datetime import timedelta

    from app.services import call_service, meeting_service
    from app.utils.time import utcnow

    start = from_ or utcnow()
    end = to or start + timedelta(days=60)
    contexts: dict = {}
    items = []
    for call in meeting_service.mine(db, user, start, end):
        if call.room_id not in contexts:
            contexts[call.room_id] = room_service.get_room_context(db, call.room_id, user)
        items.append(call_service.call_out(db, contexts[call.room_id], call))
    return CallPage(items=items, total=len(items), page=1, limit=max(len(items), 1))
