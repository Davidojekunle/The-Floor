import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_room_context
from app.db.session import get_db
from app.permissions.rules import RoomContext
from app.schemas.common import PageParams, page_params_large
from app.schemas.task import TaskDetail
from app.schemas.template import TemplateApply, TemplateCreate, TemplateOut, TemplatePage, TemplateUpdate
from app.services import template_service

router = APIRouter()


@router.get("", response_model=TemplatePage)
def list_templates(
    params: PageParams = Depends(page_params_large),
    ctx: RoomContext = Depends(get_room_context),
    db: Session = Depends(get_db),
):
    items, total = template_service.list_templates(db, ctx, params)
    return TemplatePage(items=items, total=total, page=params.page, limit=params.limit)


@router.post("", response_model=TemplateOut, status_code=201)
def create_template(body: TemplateCreate, ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)):
    return template_service.create_template(db, ctx, body)


@router.get("/{template_id}", response_model=TemplateOut)
def get_template(template_id: uuid.UUID, ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)):
    return template_service.get_template(db, ctx, template_id)


@router.patch("/{template_id}", response_model=TemplateOut)
def update_template(
    template_id: uuid.UUID, body: TemplateUpdate, ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)
):
    return template_service.update_template(db, ctx, template_id, body)


@router.delete("/{template_id}", status_code=204)
def delete_template(template_id: uuid.UUID, ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)):
    template_service.delete_template(db, ctx, template_id)
    return Response(status_code=204)


@router.post("/{template_id}/apply", response_model=TaskDetail, status_code=201)
def apply_template(
    template_id: uuid.UUID, body: TemplateApply, ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)
):
    return template_service.apply_template(db, ctx, template_id, body)
