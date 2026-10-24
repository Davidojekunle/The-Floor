"""The one place that talks to the video provider (LiveKit Cloud). Switching providers later means changing this
file and the call component, nothing else. Tests use FakeVideo (VIDEO_PROVIDER=fake), so they never start real calls.

LiveKit's server API: https://docs.livekit.io/reference/server/server-apis/ (Twirp: POST /twirp/livekit.RoomService/…,
authorised by a short JWT we sign with the API secret). Join passes are JWTs too, signed here: no network call.
The free Build plan has a hard monthly cap: past it, new calls fail instead of costing money.
"""
import base64
import hashlib
import hmac
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
import jwt

from app.core.config import get_settings
from app.core.errors import CallProviderUnavailable

logger = logging.getLogger("taskroom.calls")
UNAVAILABLE = "Calls are unavailable right now. Try again in a minute."


@dataclass
class Present:
    """Someone in a call right now, as the provider sees it."""

    session_id: str
    user_id: str | None
    joined_at: datetime


def server_url() -> str:
    """Where browsers connect (wss://<project>.livekit.cloud)."""
    return get_settings().livekit_url


def _sign(grants: dict, *, identity: str = "the-floor-server", name: str | None = None, ttl: int = 60,
          expires_at: datetime | None = None) -> str:
    s, now = get_settings(), int(time.time())
    claims = {"iss": s.livekit_api_key, "sub": identity, "nbf": now - 10, "video": grants,
              "exp": int(expires_at.timestamp()) if expires_at else now + ttl}
    if name:
        claims["name"] = name
    return jwt.encode(claims, s.livekit_api_secret, algorithm="HS256")


class LiveKitVideo:
    def _call(self, method: str, body: dict, grants: dict) -> dict:
        host = server_url().replace("wss://", "https://").replace("ws://", "http://").rstrip("/")
        try:
            r = httpx.post(f"{host}/twirp/livekit.RoomService/{method}", json=body, timeout=10,
                           headers={"Authorization": f"Bearer {_sign(grants)}"})
        except httpx.HTTPError as e:
            logger.warning("LiveKit %s failed: %s", method, e)
            raise CallProviderUnavailable(UNAVAILABLE)
        if r.status_code == 404:
            return {}
        if r.status_code >= 400:
            logger.warning("LiveKit %s answered %s: %s", method, r.status_code, r.text[:300])
            raise CallProviderUnavailable(UNAVAILABLE)
        return r.json() if r.content else {}

    def create_room(self, name: str, expires_at: datetime, max_participants: int) -> None:
        """Rooms are private by nature: only someone holding one of our passes gets in. The 3-hour hard stop is
        enforced by the minute check, which deletes the room."""
        self._call("CreateRoom", {"name": name, "max_participants": max_participants, "empty_timeout": 600,
                                  "departure_timeout": 120}, {"roomCreate": True})

    def token(self, room: str, *, user_id: str, user_name: str, expires_at: datetime, owner: bool) -> str:
        return _sign({"roomJoin": True, "room": room, "canPublish": True, "canSubscribe": True,
                      "canPublishData": True, "roomAdmin": owner},
                     identity=user_id, name=user_name[:100], expires_at=expires_at)

    def delete_room(self, room: str) -> None:
        """Ends the meeting for anyone still in it. Best effort: an empty room also closes itself."""
        try:
            self._call("DeleteRoom", {"room": room}, {"roomCreate": True})
        except CallProviderUnavailable:
            pass

    def eject(self, room: str, user_ids: list[str]) -> None:
        for identity in user_ids:  # a person can be in from two tabs, but they share one identity
            try:
                self._call("RemoveParticipant", {"room": room, "identity": identity}, {"roomAdmin": True, "room": room})
            except CallProviderUnavailable:
                pass  # their pass still runs out at the hard stop

    def presence(self, room: str) -> list[Present]:
        data = self._call("ListParticipants", {"room": room}, {"roomAdmin": True, "room": room})
        return [
            Present(session_id=p["sid"], user_id=p.get("identity"), joined_at=epoch(p.get("joined_at") or time.time()))
            for p in data.get("participants", [])
        ]


@dataclass
class FakeVideo:
    """Remembers what it was asked; tests set who is "in" a room with `present`."""

    rooms: dict = field(default_factory=dict)  # name -> expires_at
    deleted: list = field(default_factory=list)
    ejected: list = field(default_factory=list)  # (room, [user_ids])
    present: dict = field(default_factory=dict)  # name -> [Present]
    down: bool = False

    def _check(self):
        if self.down:
            raise CallProviderUnavailable(UNAVAILABLE)

    def create_room(self, name, expires_at, max_participants):
        self._check()
        self.rooms[name] = expires_at

    def token(self, room, *, user_id, user_name, expires_at, owner):
        self._check()
        return f"fake-token:{room}:{user_id}:{int(owner)}"

    def delete_room(self, room):
        self.deleted.append(room)
        self.rooms.pop(room, None)

    def eject(self, room, user_ids):
        if user_ids:
            self.ejected.append((room, list(user_ids)))

    def presence(self, room):
        self._check()
        return list(self.present.get(room, []))


_fake = FakeVideo()


def provider():
    return _fake if get_settings().video_provider == "fake" else LiveKitVideo()


def reset_fake() -> FakeVideo:
    global _fake
    _fake = FakeVideo()
    return _fake


# ------------------------------------------------------------------ webhooks

def signature_ok(raw_body: bytes, authorization: str | None) -> bool:
    """LiveKit sends a JWT signed with our API secret whose `sha256` claim is the base64 SHA-256 of the body."""
    s = get_settings()
    if not (s.livekit_api_secret and authorization):
        return False
    token = authorization.removeprefix("Bearer ").strip()
    try:
        claims = jwt.decode(token, s.livekit_api_secret, algorithms=["HS256"], options={"verify_aud": False})
    except jwt.PyJWTError:
        return False
    if claims.get("iss") != s.livekit_api_key:
        return False
    digest = base64.b64encode(hashlib.sha256(raw_body).digest()).decode()
    return hmac.compare_digest(digest, str(claims.get("sha256", "")))


def epoch(seconds) -> datetime:
    return datetime.fromtimestamp(float(seconds), tz=timezone.utc)
