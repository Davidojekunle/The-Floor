"""GET /api/v1/ws: one socket per tab, pushing small hints (never data)."""
import asyncio
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.errors import Unauthenticated
from app.core.ratelimit import MINUTE, client_ip, limiter
from app.core.errors import RateLimited
from app.core.security import decode_access_token_claims, token_predates_sign_out
from app.db.session import get_db
from app.models.enums import MembershipStatus
from app.models.room import Membership
from app.models.user import User
from app.realtime.expiry import watcher
from app.realtime.hub import hub

router = APIRouter()

CLOSE_UNAUTHENTICATED = 4401
CLOSE_RATE_LIMITED = 4429


def _session_factory(ws: WebSocket):
    return ws.app.dependency_overrides.get(get_db, get_db)


def _authenticate(factory, token: str):
    """Runs in a worker thread. The database session is closed before the socket starts listening."""
    claims = decode_access_token_claims(token)
    try:
        user_id = uuid.UUID(claims["sub"])
    except ValueError:
        raise Unauthenticated("Invalid token.")
    gen = factory()
    db = next(gen)
    try:
        user = db.get(User, user_id)
        if user is None:
            raise Unauthenticated("Account no longer exists.")
        if token_predates_sign_out(claims, user):
            raise Unauthenticated("You were signed out.")
        rooms = [
            str(r) for r in db.scalars(
                select(Membership.room_id).where(Membership.user_id == user_id, Membership.status == MembershipStatus.ACTIVE)
            )
        ]
    finally:
        gen.close()
    return user_id, rooms, datetime.fromtimestamp(claims["exp"], tz=timezone.utc)


@router.websocket("/ws")
async def live_updates(ws: WebSocket):
    settings = get_settings()
    await ws.accept()
    try:
        limiter.hit(f"ws:ip:{client_ip(ws)}", 200, MINUTE)  # loose flood guard: shared networks are fine
    except RateLimited:
        await ws.close(code=CLOSE_RATE_LIMITED)
        return
    try:
        first = await asyncio.wait_for(ws.receive_text(), timeout=settings.ws_auth_timeout_seconds)
        message = json.loads(first)
        if not isinstance(message, dict) or message.get("type") != "auth" or not isinstance(message.get("token"), str):
            raise Unauthenticated("The first message must be {\"type\": \"auth\", \"token\": \"...\"}.")
        user_id, rooms, expires = await run_in_threadpool(_authenticate, _session_factory(ws), message["token"])
    except (asyncio.TimeoutError, Unauthenticated, ValueError):
        await ws.close(code=CLOSE_UNAUTHENTICATED)
        return
    except WebSocketDisconnect:
        return

    try:
        limiter.hit(f"ws:user:{user_id}", 10, MINUTE)
    except RateLimited:
        await ws.close(code=CLOSE_RATE_LIMITED)
        return

    loop = asyncio.get_running_loop()
    hub.register(user_id, ws, loop)
    watcher.ensure_running(loop, _session_factory(ws), settings.temp_head_expiry_check_seconds)

    async def close_at_expiry():
        delay = (expires - datetime.now(timezone.utc)).total_seconds()  # reads the latest `expires`
        await asyncio.sleep(max(delay, 0))
        await ws.close(code=CLOSE_UNAUTHENTICATED)

    expiry_task = loop.create_task(close_at_expiry())
    try:
        await ws.send_json({"type": "ready", "rooms": rooms})
        while True:
            text = await ws.receive_text()
            try:
                incoming = json.loads(text)
            except ValueError:
                continue
            if not isinstance(incoming, dict):
                continue
            if incoming.get("type") == "ping":
                await ws.send_json({"type": "pong"})
            elif incoming.get("type") == "auth":
                # re-auth after a refresh: same user only; moves the expiry, no reconnect needed
                try:
                    token = incoming.get("token")
                    if not isinstance(token, str):
                        raise Unauthenticated("Missing token.")
                    new_user, _, new_expires = await run_in_threadpool(_authenticate, _session_factory(ws), token)
                    if new_user != user_id:
                        raise Unauthenticated("A socket can't change owner.")
                except Unauthenticated:
                    await ws.close(code=CLOSE_UNAUTHENTICATED)
                    break
                expires = new_expires
                expiry_task.cancel()
                expiry_task = loop.create_task(close_at_expiry())
                await ws.send_json({"type": "reauthed", "expires_at": expires.strftime("%Y-%m-%dT%H:%M:%SZ")})
            # anything else from the client is ignored: the socket is server -> client
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        expiry_task.cancel()
        hub.unregister(user_id, ws)
