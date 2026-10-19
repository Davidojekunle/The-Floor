import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_room_context
from app.db.session import get_db
from app.permissions.rules import RoomContext
from app.schemas.common import PageParams, page_params_large
from app.schemas.member import TagCreate, TagOut, TagPage, TagUpdate
from app.services import tag_service

router = APIRouter()


@router.get("", response_model=TagPage)
def list_tags(
    params: PageParams = Depends(page_params_large),
    ctx: RoomContext = Depends(get_room_context),
    db: Session = Depends(get_db),
):
    items, total = tag_service.list_tags(db, ctx, params)
    return TagPage(items=items, total=total, page=params.page, limit=params.limit)


@router.post("", response_model=TagOut, status_code=201)
def create_tag(body: TagCreate, ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)):
    return tag_service.create_tag(db, ctx, body.name)


@router.patch("/{tag_id}", response_model=TagOut)
def rename_tag(
    tag_id: uuid.UUID, body: TagUpdate, ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)
):
    return tag_service.rename_tag(db, ctx, tag_id, body.name)


@router.delete("/{tag_id}", status_code=204)
def delete_tag(tag_id: uuid.UUID, ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)):
    tag_service.delete_tag(db, ctx, tag_id)
    return Response(status_code=204)
