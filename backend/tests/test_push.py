"""Browser push: subscriptions, what gets pushed, and cleanup."""
import base64
import json
from types import SimpleNamespace

import pytest
from pywebpush import WebPushException
from sqlalchemy import select

from app.models.push import PushSubscription
from app.services import push_service
from tests.conftest import auth_headers, create_room, request_join

API = "/api/v1"
FCM = "https://fcm.googleapis.com/fcm/send/abc123"
KEYS = {"p256dh": "B" + "x" * 86, "auth": "a" * 22}


@pytest.fixture
def pushes(monkeypatch):
    """Send synchronously and record what would have gone to the push services."""
    sent = []

    def fake_webpush(subscription_info, data, **kwargs):
        sent.append((subscription_info["endpoint"], json.loads(data)))

    monkeypatch.setattr("pywebpush.webpush", fake_webpush)
    monkeypatch.setattr(push_service._pool, "submit", lambda fn, *args: fn(*args))
    return sent


def subscribe(client, headers, endpoint=FCM):
    return client.post(f"{API}/push/subscriptions", json={"endpoint": endpoint, "keys": KEYS}, headers=headers)


def subs(db):
    db.expire_all()
    return db.scalars(select(PushSubscription)).all()


def test_config_gives_a_stable_p256_public_key(client):
    h = auth_headers(client)
    first = client.get(f"{API}/push/config", headers=h).json()["public_key"]
    raw = base64.urlsafe_b64decode(first + "=" * (-len(first) % 4))
    assert len(raw) == 65 and raw[0] == 4  # an uncompressed P-256 point
    assert client.get(f"{API}/push/config", headers=h).json()["public_key"] == first


def test_config_needs_sign_in(client):
    assert client.get(f"{API}/push/config").status_code == 401


@pytest.mark.parametrize("endpoint", [
    "http://fcm.googleapis.com/x",          # not https
    "https://evil.example.com/push",        # not a push service
    "https://fcm.googleapis.com.evil.com/x",  # look-alike host
    "https://169.254.169.254/latest",       # internal address
])
def test_only_real_push_services_are_accepted(client, endpoint):
    h = auth_headers(client)
    r = subscribe(client, h, endpoint)
    assert r.status_code == 422
    assert r.json()["error"]["fields"]["endpoint"]


def test_subscribe_is_idempotent_and_moves_between_accounts(client, db):
    ada = auth_headers(client)
    femi = auth_headers(client, email="femi@example.com", name="Femi")
    assert subscribe(client, ada).status_code == 204
    assert subscribe(client, ada).status_code == 204
    assert len(subs(db)) == 1
    assert subscribe(client, femi).status_code == 204  # Femi signs in on the same browser
    (row,) = subs(db)
    assert str(row.user_id) == client.get(f"{API}/me", headers=femi).json()["id"]


def test_remove(client, db):
    h = auth_headers(client)
    subscribe(client, h)
    assert client.post(f"{API}/push/subscriptions/remove", json={"endpoint": FCM}, headers=h).status_code == 204
    assert subs(db) == []
    assert client.post(f"{API}/push/subscriptions/remove", json={"endpoint": FCM}, headers=h).status_code == 204


def test_a_notification_is_pushed_after_commit(client, pushes):
    head = auth_headers(client, email="head@example.com", name="Ada")
    room = create_room(client, head)
    subscribe(client, head)
    femi = auth_headers(client, email="femi@example.com", name="Femi")
    assert request_join(client, femi, room["invite_code"]).status_code == 201
    ((endpoint, payload),) = pushes
    assert endpoint == FCM
    assert payload["title"] == "Femi asked to join Studio Alpha"
    assert payload["url"] == f"/rooms/{room['id']}/requests"
    assert payload["body"] is None  # the title already names the room
    assert payload["tag"]


def test_category_switch_and_mute_silence_push(client, pushes):
    head = auth_headers(client, email="head@example.com", name="Ada")
    room = create_room(client, head)
    subscribe(client, head)
    client.patch(f"{API}/me/notification-settings", json={"requests": False}, headers=head)
    request_join(client, auth_headers(client, email="femi@example.com", name="Femi"), room["invite_code"])
    assert pushes == []

    client.patch(f"{API}/me/notification-settings", json={"requests": True}, headers=head)
    client.put(f"{API}/me/notification-settings/muted-rooms/{room['id']}", headers=head)
    request_join(client, auth_headers(client, email="tola@example.com", name="Tola"), room["invite_code"])
    assert pushes == []


def test_email_off_still_pushes(client, pushes):
    head = auth_headers(client, email="head@example.com", name="Ada")
    room = create_room(client, head)
    subscribe(client, head)
    client.patch(f"{API}/me/notification-settings", json={"email_enabled": False}, headers=head)
    request_join(client, auth_headers(client, email="femi@example.com", name="Femi"), room["invite_code"])
    assert len(pushes) == 1


def test_a_gone_subscription_is_deleted(client, db, monkeypatch):
    def gone(**kwargs):
        raise WebPushException("Gone", response=SimpleNamespace(status_code=410, text=""))

    monkeypatch.setattr("pywebpush.webpush", lambda *a, **k: gone(**k))
    monkeypatch.setattr(push_service._pool, "submit", lambda fn, *args: fn(*args))
    head = auth_headers(client, email="head@example.com", name="Ada")
    room = create_room(client, head)
    subscribe(client, head)
    request_join(client, auth_headers(client, email="femi@example.com", name="Femi"), room["invite_code"])
    assert subs(db) == []


def test_sign_out_everywhere_forgets_every_browser(client, db):
    h = auth_headers(client)
    subscribe(client, h)
    subscribe(client, h, "https://updates.push.services.mozilla.com/wpush/v2/xyz")
    assert client.post(f"{API}/auth/logout-all", headers={**h, "X-Taskroom-Client": "web"}).status_code == 204
    assert subs(db) == []


def test_nothing_is_pushed_when_disabled(client, pushes, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "push_enabled", False)
    head = auth_headers(client, email="head@example.com", name="Ada")
    room = create_room(client, head)
    subscribe(client, head)
    request_join(client, auth_headers(client, email="femi@example.com", name="Femi"), room["invite_code"])
    assert pushes == []
