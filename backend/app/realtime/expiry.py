"""Temp head grants expire with nobody acting, so a small loop announces them."""
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.models.room import TempHead
from app.realtime import events
from app.realtime.hub import hub
from app.utils.time import utcnow

logger = logging.getLogger("taskroom.realtime")


def expired_grant_events(db: Session, since: datetime, until: datetime) -> list[tuple[dict, set]]:
    """room_changed for every room where an active grant expired in (since, until]."""
    room_ids = set(
        db.scalars(
            select(TempHead.room_id).where(
                TempHead.revoked_at.is_(None), TempHead.expires_at > since, TempHead.expires_at <= until
            )
        )
    )
    return [({"type": "room_changed", "room_id": str(rid)}, events.room_members(db, rid)) for rid in room_ids]


class ExpiryWatcher:
    """One per event loop. Started by the first WebSocket that connects."""

    def __init__(self) -> None:
        self._tasks: dict = {}

    def ensure_running(self, loop, session_factory, interval: float) -> None:
        task = self._tasks.get(loop)
        if task is None or task.done():
            self._tasks[loop] = loop.create_task(self._run(session_factory, interval))

    async def _run(self, session_factory, interval: float) -> None:
        last = utcnow()
        while True:
            await asyncio.sleep(interval)
            now = utcnow()
            if not hub.is_empty():
                try:
                    found = await run_in_threadpool(self._check, session_factory, last, now)
                    hub.publish(found)
                except Exception:
                    logger.exception("temp head expiry check failed")
            last = now

    @staticmethod
    def _check(session_factory, since, until):
        gen = session_factory()
        db = next(gen)
        try:
            return expired_grant_events(db, since, until)
        finally:
            gen.close()


watcher = ExpiryWatcher()
