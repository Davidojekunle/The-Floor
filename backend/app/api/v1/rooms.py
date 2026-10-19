import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_room_context
from app.db.session import get_db
from app.models.user import User
from app.permissions.rules import RoomContext
from app.schemas.common import PageParams, page_params
from app.schemas.room import (
    DeleteRoom,
    TransferHead,
    InviteOut,
    JoinRequestPage,
    MembershipOut,
    RoomCreate,
    RoomOut,
    RoomSummaryPage,
)
from app.services import lifecycle_service, room_service

router = APIRouter()


@router.post("", response_model=RoomOut, status_code=201)
def create_room(body: RoomCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ctx = room_service.create_room(db, user, body.name)
    return room_service.room_out(db, ctx)


@router.get("", response_model=RoomSummaryPage)
def list_my_rooms(
    params: PageParams = Depends(page_params),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rooms = room_service.list_rooms_for_user(db, user)
    page = rooms[params.offset : params.offset + params.limit]
    return RoomSummaryPage(items=page, total=len(rooms), page=params.page, limit=params.limit)


@router.get("/{room_id}", response_model=RoomOut)
def get_room(ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)):
    return room_service.room_out(db, ctx)


@router.post("/{room_id}/invite/regenerate", response_model=InviteOut)
def regenerate_invite(ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)):
    return room_service.regenerate_invite(db, ctx)


@router.get("/{room_id}/join-requests", response_model=JoinRequestPage)
def list_join_requests(
    params: PageParams = Depends(page_params),
    ctx: RoomContext = Depends(get_room_context),
    db: Session = Depends(get_db),
):
    items, total = room_service.list_join_requests(db, ctx, params)
    return JoinRequestPage(items=items, total=total, page=params.page, limit=params.limit)


@router.post("/{room_id}/join-requests/{membership_id}/approve", response_model=MembershipOut)
def approve_join_request(
    membership_id: uuid.UUID, ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)
):
    return room_service.decide_join_request(db, ctx, membership_id, approve=True)


@router.post("/{room_id}/join-requests/{membership_id}/reject", response_model=MembershipOut)
def reject_join_request(
    membership_id: uuid.UUID, ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)
):
    return room_service.decide_join_request(db, ctx, membership_id, approve=False)


# ------------------------------------------------------------------ lifecycle

@router.post("/{room_id}/leave", status_code=204)
def leave_room(ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)):
    lifecycle_service.leave_room(db, ctx)
    return Response(status_code=204)


@router.post("/{room_id}/transfer-head", response_model=RoomOut)
def transfer_head(
    body: TransferHead,
    ctx: RoomContext = Depends(get_room_context),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    lifecycle_service.transfer_head(db, ctx, body.membership_id)
    return room_service.room_out(db, room_service.get_room_context(db, ctx.room.id, user))  # your new role


@router.delete("/{room_id}", status_code=204)
def delete_room(body: DeleteRoom, ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)):
    lifecycle_service.delete_room(db, ctx, body.confirm_name)
    return Response(status_code=204)
