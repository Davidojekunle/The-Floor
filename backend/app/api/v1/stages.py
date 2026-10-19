import uuid

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_room_context
from app.db.session import get_db
from app.permissions.rules import RoomContext
from app.core.openapi import err
from app.schemas.task import NudgeIn, StageCreate, StageUpdate, StatusUpdate, TaskDetail
from app.schemas.progress import UpdateCreate, UpdateOut, UpdatePage
from app.services import nudge_service, progress_service, stage_service

router = APIRouter()
# Every route here returns the FULL updated task, so the UI never shows stale progress.


@router.post("", response_model=TaskDetail, status_code=201)
def add_stage(
    task_id: uuid.UUID, body: StageCreate, ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)
):
    return stage_service.add_stage(db, ctx, task_id, body)


@router.patch("/{stage_id}", response_model=TaskDetail)
def update_stage(
    task_id: uuid.UUID,
    stage_id: uuid.UUID,
    body: StageUpdate,
    ctx: RoomContext = Depends(get_room_context),
    db: Session = Depends(get_db),
):
    return stage_service.update_stage(db, ctx, task_id, stage_id, body)


@router.put("/{stage_id}/status", response_model=TaskDetail)
def put_stage_status(
    task_id: uuid.UUID,
    stage_id: uuid.UUID,
    body: StatusUpdate,
    ctx: RoomContext = Depends(get_room_context),
    db: Session = Depends(get_db),
):
    return stage_service.set_status(db, ctx, task_id, stage_id, body)


@router.delete("/{stage_id}", response_model=TaskDetail)
def delete_stage(
    task_id: uuid.UUID, stage_id: uuid.UUID, ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)
):
    return stage_service.delete_stage(db, ctx, task_id, stage_id)


# ------------------------------------------------------------------ nudges

@router.post("/{stage_id}/nudge", response_model=TaskDetail, responses={
    403: err("Only a head or temp head can nudge."),
    409: err("NOT_NUDGEABLE: not late, stuck or blocked. ALREADY_NUDGED: nudged in the last 24 hours. "
             "NOBODY_ON_STAGE: nobody is on it yet. TASK_NOT_APPROVED."),
})
def nudge_stage(
    task_id: uuid.UUID,
    stage_id: uuid.UUID,
    body: NudgeIn | None = None,
    ctx: RoomContext = Depends(get_room_context),
    db: Session = Depends(get_db),
):
    """Privately ask the people on a late, stuck (3+ days) or blocked stage for an update. Never posted in chat."""
    return nudge_service.nudge(db, ctx, task_id, stage_id, body.note if body else None)


@router.post("/{stage_id}/nudge/ack", response_model=TaskDetail, responses={403: err("You're not on this stage.")})
def acknowledge_nudge(
    task_id: uuid.UUID, stage_id: uuid.UUID, ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)
):
    """“I'm on it”: starts a To do stage, or answers the nudge on one already in progress."""
    return nudge_service.acknowledge(db, ctx, task_id, stage_id)


# ------------------------------------------------------------------ progress updates (phase 6b)

@router.get("/{stage_id}/updates", response_model=UpdatePage)
def list_stage_updates(
    task_id: uuid.UUID,
    stage_id: uuid.UUID,
    before: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ctx: RoomContext = Depends(get_room_context),
    db: Session = Depends(get_db),
):
    return progress_service.list_stage_updates(db, ctx, task_id, stage_id, before, limit)


@router.post("/{stage_id}/updates", response_model=UpdateOut, status_code=201)
def post_stage_update(
    task_id: uuid.UUID,
    stage_id: uuid.UUID,
    body: UpdateCreate,
    ctx: RoomContext = Depends(get_room_context),
    db: Session = Depends(get_db),
):
    return progress_service.post_update(db, ctx, task_id, stage_id, body)


@router.delete("/{stage_id}/updates/{update_id}", status_code=204)
def delete_stage_update(
    task_id: uuid.UUID,
    stage_id: uuid.UUID,
    update_id: uuid.UUID,
    ctx: RoomContext = Depends(get_room_context),
    db: Session = Depends(get_db),
):
    progress_service.delete_update(db, ctx, task_id, stage_id, update_id)
    return Response(status_code=204)
