from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.v1 import auth, join, me, rooms
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
api_router.include_router(rooms.router, prefix="/rooms", tags=["rooms"])
api_router.include_router(join.router, prefix="/join", tags=["join"])
