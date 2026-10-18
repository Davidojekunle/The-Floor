import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_room_context
from app.db.session import get_db
from app.permissions.rules import RoomContext
from app.schemas.common import PageParams, page_params
from app.schemas.member import MemberOut, MemberPage, MemberTagsUpdate, TempHeadGrant
from app.services import member_service

router = APIRouter()


@router.get("", response_model=MemberPage)
def list_members(
    tag: uuid.UUID | None = Query(None, description="Only members holding this tag"),
    role: Literal["head", "temp_head", "member"] | None = Query(None, description="Effective role"),
    params: PageParams = Depends(page_params),
    ctx: RoomContext = Depends(get_room_context),
    db: Session = Depends(get_db),
):
    items, total = member_service.list_members(db, ctx, params, tag_id=tag, role=role)
    return MemberPage(items=items, total=total, page=params.page, limit=params.limit)


@router.patch("/{membership_id}", response_model=MemberOut)
def set_member_tags(
    membership_id: uuid.UUID,
    body: MemberTagsUpdate,
    ctx: RoomContext = Depends(get_room_context),
    db: Session = Depends(get_db),
):
    return member_service.set_member_tags(db, ctx, membership_id, body.tag_ids)


@router.delete("/{membership_id}", status_code=204)
def remove_member(
    membership_id: uuid.UUID, ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)
):
    member_service.remove_member(db, ctx, membership_id)
    return Response(status_code=204)


@router.put("/{membership_id}/temp-head", response_model=MemberOut)
def set_temp_head(
    membership_id: uuid.UUID,
    body: TempHeadGrant,
    ctx: RoomContext = Depends(get_room_context),
    db: Session = Depends(get_db),
):
    return member_service.set_temp_head(db, ctx, membership_id, body.expires_at)


@router.delete("/{membership_id}/temp-head", status_code=204)
def revoke_temp_head(
    membership_id: uuid.UUID, ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)
):
    member_service.revoke_temp_head(db, ctx, membership_id)
    return Response(status_code=204)
