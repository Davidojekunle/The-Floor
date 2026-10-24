"""The one place that talks to the video provider (Daily). Switching providers later means changing this file
and the call component, nothing else. Tests use FakeVideo (VIDEO_PROVIDER=fake), so they never start real calls.

Daily's REST API: https://docs.daily.co/reference/rest-api
"""
import base64
import hashlib
import hmac
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

from app.core.config import get_settings
from app.core.errors import CallProviderUnavailable

logger = logging.getLogger("taskroom.calls")
API = "https://api.daily.co/v1"


@dataclass
class Present:
    """Someone in a call right now, as the provider sees it."""

    session_id: str
    user_id: str | None
    joined_at: datetime


def room_url(name: str) -> str:
    return f"https://{get_settings().daily_domain}.daily.co/{name}"


class DailyVideo:
    def _call(self, method: str, path: str, json: dict | None = None) -> httpx.Response:
        try:
            r = httpx.request(method, f"{API}{path}", json=json, timeout=10,
                              headers={"Authorization": f"Bearer {get_settings().daily_api_key}"})
        except httpx.HTTPError as e:
            logger.warning("Daily %s %s failed: %s", method, path, e)
            raise CallProviderUnavailable("Calls are unavailable right now. Try again in a minute.")
        if r.status_code >= 500 or r.status_code in (401, 403, 429):
            logger.warning("Daily %s %s answered %s: %s", method, path, r.status_code, r.text[:300])
            raise CallProviderUnavailable("Calls are unavailable right now. Try again in a minute.")
        return r

    def create_room(self, name: str, expires_at: datetime, max_participants: int) -> None:
        """Private, so only someone holding one of our passes gets in. Everyone is put out at the hard stop."""
        r = self._call("POST", "/rooms", {
            "name": name,
            "privacy": "private",
            "properties": {
                "exp": int(expires_at.timestamp()),
                "eject_at_room_exp": True,
                "max_participants": max_participants,
                "enable_prejoin_ui": True,
                "enable_screenshare": True,
                "enable_chat": True,
            },
        })
        if r.status_code >= 400:
            logger.warning("Daily create room answered %s: %s", r.status_code, r.text[:300])
            raise CallProviderUnavailable("Calls are unavailable right now. Try again in a minute.")

    def token(self, room: str, *, user_id: str, user_name: str, expires_at: datetime, owner: bool) -> str:
        r = self._call("POST", "/meeting-tokens", {"properties": {
            "room_name": room, "user_id": user_id, "user_name": user_name[:100],
            "exp": int(expires_at.timestamp()), "is_owner": owner, "eject_at_token_exp": True,
        }})
        if r.status_code >= 400:
            logger.warning("Daily token answered %s: %s", r.status_code, r.text[:300])
            raise CallProviderUnavailable("Calls are unavailable right now. Try again in a minute.")
        return r.json()["token"]

    def delete_room(self, room: str) -> None:
        """Ends the meeting for anyone still in it. Best effort: the room expires on its own at the hard stop."""
        try:
            self._call("DELETE", f"/rooms/{room}")
        except CallProviderUnavailable:
            pass

    def eject(self, room: str, user_ids: list[str]) -> None:
        if user_ids:
            try:
                self._call("POST", f"/rooms/{room}/eject", {"user_ids": user_ids[:100]})
            except CallProviderUnavailable:
                pass  # their pass still runs out at the hard stop

    def presence(self, room: str) -> list[Present]:
        r = self._call("GET", f"/rooms/{room}/presence")
        if r.status_code == 404:
            return []
        return [
            Present(session_id=p["id"], user_id=p.get("userId"),
                    joined_at=datetime.fromisoformat(p["joinTime"].replace("Z", "+00:00")))
            for p in r.json().get("data", [])
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
            raise CallProviderUnavailable("Calls are unavailable right now. Try again in a minute.")

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
    return _fake if get_settings().video_provider == "fake" else DailyVideo()


def reset_fake() -> FakeVideo:
    global _fake
    _fake = FakeVideo()
    return _fake


# ------------------------------------------------------------------ webhooks

def signature_ok(raw_body: bytes, timestamp: str | None, signature: str | None) -> bool:
    """Daily signs `timestamp + "." + body` with HMAC-SHA256, keyed by the base64-decoded secret, base64 out."""
    secret = get_settings().daily_webhook_secret
    if not (secret and timestamp and signature):
        return False
    try:
        key = base64.b64decode(secret)
    except ValueError:
        return False
    expected = base64.b64encode(hmac.new(key, timestamp.encode() + b"." + raw_body, hashlib.sha256).digest()).decode()
    return hmac.compare_digest(expected, signature)


def epoch(seconds) -> datetime:
    return datetime.fromtimestamp(float(seconds), tz=timezone.utc)
