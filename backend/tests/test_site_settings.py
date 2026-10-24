"""Site switches on the admin page: calls (off / staff / everyone), sign-ups, emails, digest, push, announcement."""
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.core.config import get_settings
from app.models.email import OutboxEmail
from app.models.user import User
from app.services import notification_email, video
from app.utils.time import utcnow
from tests.conftest import CLIENT_HEADER, auth_headers, make_team, request_join

API = "/api/v1"


def staff(db, email):
    db.execute(update(User).where(User.email == email).values(is_staff=True))
    db.commit()


def put(client, headers, **change):
    return client.patch(f"{API}/admin/settings", json=change, headers=headers)


@pytest.fixture
def provider(monkeypatch):
    """LiveKit 'configured' (faked): calls follow the admin switch (CALLS_ENABLED stays off, as on the live site)."""
    monkeypatch.setattr(get_settings(), "video_provider", "fake")
    return video.reset_fake()


def test_only_staff_see_or_change_settings(client, db):
    team = make_team(client)
    assert client.get(f"{API}/admin/settings", headers=team.head).status_code == 404
    staff(db, "head@example.com")
    s = client.get(f"{API}/admin/settings", headers=team.head).json()
    assert s == {"calls": "off", "calls_ready": False, "signups_open": True, "notification_emails": True,
                 "daily_digest": True, "push": True, "announcement": None}


def test_calls_cant_be_switched_on_without_livekit(client, db):
    team = make_team(client)
    staff(db, "head@example.com")
    r = put(client, team.head, calls="staff")
    assert r.status_code == 409


def test_staff_only_then_everyone(client, db, provider):
    team = make_team(client)
    staff(db, "head@example.com")
    assert put(client, team.head, calls="staff").json()["calls"] == "staff"
    me = lambda h: client.get(f"{API}/me", headers=h).json()["calls_enabled"]  # noqa: E731
    assert me(team.head) is True and me(team.tola) is False
    assert client.post(f"{API}/rooms/{team.room['id']}/calls", json={}, headers=team.tola).status_code == 404
    assert client.post(f"{API}/rooms/{team.room['id']}/calls", json={}, headers=team.head).status_code == 201
    msgs = client.get(f"{API}/rooms/{team.room['id']}/messages", headers=team.tola).json()["items"]
    assert not any(m["event"] and m["event"]["type"] == "call_started" for m in msgs)  # testing stays quiet
    tola_bell = client.get(f"{API}/me/notifications", headers=team.tola).json()["items"]
    assert not any(n["type"] == "call_started" for n in tola_bell)

    assert put(client, team.head, calls="everyone").json()["calls"] == "everyone"
    assert me(team.tola) is True
    stats = client.get(f"{API}/admin/stats", headers=team.head).json()["calls"]
    assert stats["mode"] == "everyone" and stats["ready"] is True and stats["free_minutes"] == 5000


def test_closed_sign_ups_still_let_invited_people_in(client, db, provider):
    team = make_team(client)
    staff(db, "head@example.com")
    put(client, team.head, signups_open=False)
    assert client.get(f"{API}/site").json()["signups_open"] is False
    body = {"name": "New", "email": "new@example.com", "password": "password123", "timezone": "UTC"}
    r = client.post(f"{API}/auth/register", json=body, headers=CLIENT_HEADER)
    assert r.status_code == 403 and "closed" in r.json()["error"]["message"]
    client.post(f"{API}/rooms/{team.room['id']}/invite/email", json={"emails": ["new@example.com"]}, headers=team.head)
    assert client.post(f"{API}/auth/register", json=body, headers=CLIENT_HEADER).status_code == 201


def test_paused_notification_emails_and_digest(client, db):
    team = make_team(client)
    staff(db, "head@example.com")
    put(client, team.head, notification_emails=False)
    kemi = auth_headers(client, email="kemi@example.com", name="Kemi")
    request_join(client, kemi, team.room["invite_code"])
    notification_email.flush_due(db, utcnow() + timedelta(hours=1))
    assert db.scalars(select(OutboxEmail).where(OutboxEmail.category != "security")).all() == []
    assert notification_email.send_digests(db, utcnow() + timedelta(hours=12)) == 0
    # the bell still works
    assert any(n["type"] == "join_requested" for n in client.get(f"{API}/me/notifications", headers=team.head).json()["items"])


def test_paused_push(client, db, monkeypatch):
    import uuid

    from sqlalchemy.orm import Session

    from app.models.push import PushSubscription
    from app.services import push_service

    team = make_team(client)
    staff(db, "head@example.com")
    monkeypatch.setattr(push_service, "_pool", type("NoPool", (), {"submit": staticmethod(lambda *a, **k: None)})())
    db.add(PushSubscription(id=uuid.uuid4(), user_id=uuid.UUID(team.ids["tola"]), endpoint="https://fcm.googleapis.com/x",
                            p256dh="k" * 30, auth="a" * 12))
    db.commit()

    def queued() -> int:
        s = Session(bind=db.get_bind())
        push_service.queue(s, uuid.UUID(team.ids["tola"]), title="x", body=None, url="/", tag="t")
        n = len(s.info.get(push_service._PENDING, []))
        s.close()
        return n

    assert queued() == 1  # on: it would go
    put(client, team.head, push=False)
    assert queued() == 0  # paused for the whole site


def test_announcement(client, db):
    team = make_team(client)
    staff(db, "head@example.com")
    put(client, team.head, announcement="  New: video calls in your rooms  ")
    assert client.get(f"{API}/me", headers=team.tola).json()["announcement"] == "New: video calls in your rooms"
    assert client.get(f"{API}/site").json()["announcement"] == "New: video calls in your rooms"
    put(client, team.head, announcement="")
    assert client.get(f"{API}/site").json()["announcement"] is None
