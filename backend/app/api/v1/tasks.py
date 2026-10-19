import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_room_context
from app.db.session import get_db
from app.permissions.rules import RoomContext
from app.schemas.common import PageParams, UtcDateTime, page_params_tasks
from app.schemas.task import RejectBody, TaskCreate, TaskDetail, TaskPage, TaskUpdate
from app.schemas.progress import UpdatePage
from app.services import progress_service, task_service

router = APIRouter()


@router.post("", response_model=TaskDetail, status_code=201)
def create_task(body: TaskCreate, ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)):
    return task_service.create_task(db, ctx, body)


@router.get("", response_model=TaskPage)
def list_tasks(
    from_: Annotated[UtcDateTime | None, Query(alias="from", description="Window start, inclusive")] = None,
    to: Annotated[UtcDateTime | None, Query(description="Window end, exclusive")] = None,
    status: Annotated[Literal["not_started", "in_progress", "done"] | None, Query()] = None,
    assignee: Annotated[str | None, Query(description="A user id, or 'me'")] = None,
    tag: Annotated[uuid.UUID | None, Query(description="Only tasks with a stage that has this tag")] = None,
    overdue: Annotated[bool | None, Query()] = None,
    blocked: Annotated[bool | None, Query(description="Only tasks with a blocked stage")] = None,
    approval_status: Annotated[
        str | None,
        Query(description="Comma-separated: approved (default), pending, rejected. Non-approvers only see their own proposals."),
    ] = None,
    sort: Annotated[Literal["due_date", "submitted_at"], Query(description="submitted_at = oldest first (approvals queue)")] = "due_date",
    params: PageParams = Depends(page_params_tasks),
    ctx: RoomContext = Depends(get_room_context),
    db: Session = Depends(get_db),
):
    items, total = task_service.list_tasks(
        db, ctx, params, from_=from_, to=to, status=status, assignee=assignee, tag=tag, overdue=overdue,
        blocked=blocked, approval_status=approval_status, sort=sort,
    )
    return TaskPage(items=items, total=total, page=params.page, limit=params.limit)


@router.get("/{task_id}", response_model=TaskDetail)
def get_task(task_id: uuid.UUID, ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)):
    return task_service.get_task(db, ctx, task_id)


@router.patch("/{task_id}", response_model=TaskDetail)
def update_task(
    task_id: uuid.UUID, body: TaskUpdate, ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)
):
    return task_service.update_task(db, ctx, task_id, body)


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: uuid.UUID, ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)):
    task_service.delete_task(db, ctx, task_id)
    return Response(status_code=204)


@router.post("/{task_id}/approve", response_model=TaskDetail)
def approve_task(task_id: uuid.UUID, ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)):
    return task_service.approve_task(db, ctx, task_id)


@router.post("/{task_id}/reject", response_model=TaskDetail)
def reject_task(
    task_id: uuid.UUID,
    body: RejectBody | None = None,
    ctx: RoomContext = Depends(get_room_context),
    db: Session = Depends(get_db),
):
    return task_service.reject_task(db, ctx, task_id, body.reason if body else None)


@router.post("/{task_id}/resubmit", response_model=TaskDetail)
def resubmit_task(task_id: uuid.UUID, ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)):
    return task_service.resubmit_task(db, ctx, task_id)


@router.get("/{task_id}/updates", response_model=UpdatePage)
def list_task_updates(
    task_id: uuid.UUID,
    before: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ctx: RoomContext = Depends(get_room_context),
    db: Session = Depends(get_db),
):
    return progress_service.list_task_updates(db, ctx, task_id, before, limit)
