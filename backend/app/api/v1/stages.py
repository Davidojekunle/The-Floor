import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_room_context
from app.db.session import get_db
from app.permissions.rules import RoomContext
from app.schemas.task import StageCreate, StageUpdate, StatusUpdate, TaskDetail
from app.services import stage_service

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
