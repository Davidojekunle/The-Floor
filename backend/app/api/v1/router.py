from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.v1 import (
    admin, auth, calendar, join, me, members, messages, notifications, push, rooms, stages, tags, tasks, templates, unsubscribe, ws,
)
from app.core.openapi import AUTHED_RESPONSES
from app.db.session import get_db

api_router = APIRouter()


@api_router.get("/health", tags=["health"])
def health() -> dict:
    """Is the API up?"""
    return {"status": "ok"}


@api_router.get("/health/db", tags=["health"])
def health_db(db: Session = Depends(get_db)) -> dict:
    """Can the API reach PostgreSQL?"""
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}


api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(me.router, tags=["me"])
api_router.include_router(notifications.router, tags=["notifications"])
api_router.include_router(unsubscribe.router, tags=["notifications"])
api_router.include_router(push.router, tags=["notifications"])
api_router.include_router(calendar.router, tags=["calendar"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(rooms.router, prefix="/rooms", tags=["rooms"], responses=AUTHED_RESPONSES)
api_router.include_router(join.router, prefix="/join", tags=["join"], responses=AUTHED_RESPONSES)
api_router.include_router(tags.router, prefix="/rooms/{room_id}/tags", tags=["tags"], responses=AUTHED_RESPONSES)
api_router.include_router(members.router, prefix="/rooms/{room_id}/members", tags=["members"], responses=AUTHED_RESPONSES)
api_router.include_router(
    tasks.router, prefix="/rooms/{room_id}/tasks", tags=["tasks"], responses=AUTHED_RESPONSES
)
api_router.include_router(
    stages.router, prefix="/rooms/{room_id}/tasks/{task_id}/stages", tags=["stages"], responses=AUTHED_RESPONSES
)
api_router.include_router(
    templates.router, prefix="/rooms/{room_id}/templates", tags=["templates"], responses=AUTHED_RESPONSES
)
api_router.include_router(
    messages.router, prefix="/rooms/{room_id}/messages", tags=["chat"], responses=AUTHED_RESPONSES
)
api_router.include_router(ws.router, tags=["realtime"])
