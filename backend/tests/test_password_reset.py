"""L2: email outbox, forgotten password, and immediate sign-out everywhere."""
import re
import smtplib
import uuid
from datetime import timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from starlette.websockets import WebSocketDisconnect

from app.core.config import get_settings
from app.core.security import ALGORITHM
from app.models.email import OutboxEmail, PasswordResetToken
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services import email_service
from app.utils.time import utcnow
from tests.conftest import CLIENT_HEADER, register

API = "/api/v1"


def token_for(user_id, iat):
    return jwt.encode({"sub": str(user_id), "iat": iat, "exp": iat + 900}, get_settings().secret_key, algorithm=ALGORITHM)


def old_token(db, seconds=10):
    """An access token issued a little while ago. One minted in the same second as a
    sign-out stays valid by design (the cutoff is inclusive), so tests use older ones."""
    user = db.scalar(select(User))
    return token_for(user.id, int(utcnow().timestamp()) - seconds)




def forgot(client, email="ada@example.com", headers=CLIENT_HEADER):
    return client.post(f"{API}/auth/forgot-password", json={"email": email}, headers=headers)


def reset(client, token, password="brand-new-pass", headers=CLIENT_HEADER):
    return client.post(f"{API}/auth/reset-password", json={"token": token, "new_password": password}, headers=headers)


def login(client, password="password123", email="ada@example.com"):
    return client.post(f"{API}/auth/login", json={"email": email, "password": password}, headers=CLIENT_HEADER)


def outbox(db):
    return list(db.scalars(select(OutboxEmail).order_by(OutboxEmail.created_at)))


def token_from(email_row):
    return re.search(r"token=([A-Za-z0-9_\-]+)", email_row.text_body).group(1)


def err(r, status, code=None):
    assert r.status_code == status, r.text
    if code:
        assert r.json()["error"]["code"] == code
    return r.json()["error"]


# =========================================================== forgot password

def test_forgot_password_queues_a_link_email(client, db):
    register(client)
    r = forgot(client)
    assert r.status_code == 202
    (row,) = outbox(db)
    assert (row.to_address, row.subject, row.category) == ("ada@example.com", "Reset your password for The Floor", "security")
    assert "http://localhost:5173/reset-password?token=" in row.text_body
    assert "<html" in row.html_body and 'content="light dark"' in row.html_body
    assert row.sent_at is None


def test_unknown_email_gets_the_identical_answer_and_no_email(client, db):
    register(client)
    known, unknown = forgot(client), forgot(client, "nobody@example.com")
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert len(outbox(db)) == 1


def test_link_uses_an_allowed_origin_otherwise_frontend_url(client, db):
    register(client)
    client.post(f"{API}/auth/forgot-password", json={"email": "ada@example.com"},
                headers={**CLIENT_HEADER, "Origin": "http://localhost:5173"})
    client.post(f"{API}/auth/forgot-password", json={"email": "ada@example.com"},
                headers={**CLIENT_HEADER, "Origin": "https://evil.example.com"})
    rows = outbox(db)
    assert all("https://evil.example.com" not in r.text_body for r in rows)
    assert all("http://localhost:5173/reset-password" in r.text_body for r in rows)


def test_forgot_password_needs_the_client_header(client):
    register(client)
    err(forgot(client, headers={}), 403)


def test_at_most_three_reset_emails_an_hour_but_always_202(client, db):
    register(client)
    for _ in range(5):
        assert forgot(client).status_code == 202
    assert len(outbox(db)) == 3


def test_a_new_link_cancels_the_old_one(client, db):
    register(client)
    forgot(client)
    forgot(client)
    old, new = outbox(db)
    err(reset(client, token_from(old)), 400, "RESET_TOKEN_INVALID")
    assert reset(client, token_from(new)).status_code == 204


# =========================================================== reset password

def test_reset_changes_the_password_and_ends_every_session(client, db):
    register(client)
    login(client)  # a second device
    access = old_token(db)
    forgot(client)
    raw = token_from(outbox(db)[0])

    assert reset(client, raw).status_code == 204
    assert login(client).status_code == 401  # old password
    assert login(client, "brand-new-pass").status_code == 200
    # the old access token stops working at once, not in 15 minutes
    err(client.get(f"{API}/me", headers={"Authorization": f"Bearer {access}"}), 401, "UNAUTHENTICATED")
    old_families = db.scalars(select(RefreshToken).where(RefreshToken.revoke_reason == "logout_all")).all()
    assert len(old_families) == 1  # the second device's session
    subjects = [r.subject for r in outbox(db)]
    assert subjects[-1] == "Your password for The Floor was changed"


def test_reset_token_is_single_use_and_expires(client, db):
    register(client)
    forgot(client)
    raw = token_from(outbox(db)[0])
    reset(client, raw)
    err(reset(client, raw, "another-pass-1"), 400, "RESET_TOKEN_INVALID")

    db.execute(update(PasswordResetToken).values(created_at=utcnow() - timedelta(hours=2)))
    db.commit()
    forgot(client)
    fresh = token_from(outbox(db)[-1])
    db.execute(update(PasswordResetToken).where(PasswordResetToken.used_at.is_(None))
               .values(expires_at=utcnow() - timedelta(seconds=1)))
    db.commit()
    err(reset(client, fresh), 400, "RESET_TOKEN_INVALID")
    err(reset(client, "garbage"), 400, "RESET_TOKEN_INVALID")


def test_reset_validates_the_new_password(client, db):
    register(client)
    forgot(client)
    raw = token_from(outbox(db)[0])
    for bad in ("short", "x" * 73):
        assert "new_password" in err(reset(client, raw, bad), 422)["fields"]
    assert reset(client, raw).status_code == 204  # the token survived the failed attempts


def test_tokens_are_stored_hashed(client, db):
    register(client)
    forgot(client)
    raw = token_from(outbox(db)[0])
    row = db.scalar(select(PasswordResetToken))
    assert raw not in row.token_hash and len(row.token_hash) == 64


# =========================================================== sign-out takes effect immediately

def test_sessions_valid_after_is_inclusive(client, db):
    register(client)
    user = db.scalar(select(User))
    cutoff = utcnow().replace(microsecond=0)
    user.sessions_valid_after = cutoff
    db.commit()
    same_second = token_for(user.id, int(cutoff.timestamp()))
    one_before = token_for(user.id, int(cutoff.timestamp()) - 1)
    assert client.get(f"{API}/me", headers={"Authorization": f"Bearer {same_second}"}).status_code == 200
    assert client.get(f"{API}/me", headers={"Authorization": f"Bearer {one_before}"}).status_code == 401


def test_logout_all_now_also_kills_live_access_tokens(client, db):
    register(client)
    access = login(client).json()["access_token"]
    other = old_token(db)
    client.post(f"{API}/auth/logout-all", headers={**CLIENT_HEADER, "Authorization": f"Bearer {access}"})
    assert client.get(f"{API}/me", headers={"Authorization": f"Bearer {other}"}).status_code == 401


@pytest.fixture
def lc(app):
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_reset_closes_open_sockets_and_old_tokens_cannot_reconnect(lc, db):
    register(lc)
    access = old_token(db)
    with lc.websocket_connect(f"{API}/ws") as ws:
        ws.send_json({"type": "auth", "token": access})
        assert ws.receive_json()["type"] == "ready"
        forgot(lc)
        assert reset(lc, token_from(outbox(db)[0])).status_code == 204
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
        assert e.value.code == 4401
    with lc.websocket_connect(f"{API}/ws") as ws:
        ws.send_json({"type": "auth", "token": access})
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
        assert e.value.code == 4401


# =========================================================== the outbox

def test_nothing_is_sent_if_the_change_rolls_back(db):
    email_service.queue(db, to="x@example.com", subject="s", text="t", html_body="h", category="security")
    db.rollback()
    assert db.scalar(select(func.count()).select_from(OutboxEmail)) == 0


def test_console_delivery_marks_sent(client, db, caplog):
    register(client)
    forgot(client)
    with caplog.at_level("WARNING", logger="taskroom.email"):
        assert email_service.deliver_pending(db) == 1
    assert "Reset your password for The Floor" in caplog.text
    assert outbox(db)[0].sent_at is not None
    assert email_service.deliver_pending(db) == 0  # never twice


class Failing:
    def send(self, email):
        raise ConnectionError("smtp down")


def test_failures_back_off_and_give_up_after_three(client, db, monkeypatch):
    register(client)
    forgot(client)
    monkeypatch.setattr(email_service, "backend", lambda: Failing())
    for attempt in (1, 2, 3):
        db.execute(update(OutboxEmail).values(next_attempt_at=utcnow() - timedelta(seconds=1)))
        db.commit()
        assert email_service.deliver_pending(db) == 0
        row = outbox(db)[0]
        assert row.attempts == attempt and "smtp down" in row.last_error
    assert row.failed_at is not None
    db.execute(update(OutboxEmail).values(next_attempt_at=utcnow() - timedelta(seconds=1)))
    db.commit()
    assert email_service.deliver_pending(db) == 0 and outbox(db)[0].attempts == 3  # no more tries


def test_not_yet_due_retries_wait(client, db, monkeypatch):
    register(client)
    forgot(client)
    monkeypatch.setattr(email_service, "backend", lambda: Failing())
    email_service.deliver_pending(db)
    monkeypatch.setattr(email_service, "backend", lambda: email_service.ConsoleBackend())
    assert email_service.deliver_pending(db) == 0  # backing off: 30 seconds before the next attempt


def test_smtp_backend_builds_a_proper_message(client, db, monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent["server"] = (host, port)
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def starttls(self):
            sent["tls"] = True
        def login(self, user, password):
            sent["login"] = (user, password)
        def send_message(self, msg):
            sent["msg"] = msg

    s = get_settings()
    for k, v in {"email_backend": "smtp", "smtp_host": "smtp.example.com", "smtp_port": 587,
                 "smtp_username": "apikey", "smtp_password": "secret", "email_from": "The Floor <no-reply@taskroom.app>"}.items():
        monkeypatch.setattr(s, k, v)
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    register(client)
    forgot(client)
    assert email_service.deliver_pending(db) == 1
    msg = sent["msg"]
    assert sent["server"] == ("smtp.example.com", 587) and sent["tls"] and sent["login"] == ("apikey", "secret")
    assert (msg["From"], msg["To"], msg["Subject"]) == ("The Floor <no-reply@taskroom.app>", "ada@example.com", "Reset your password for The Floor")
    assert msg.get_content_type() == "multipart/alternative"


def test_resend_backend_posts_to_the_api(client, db, monkeypatch):
    calls = []

    class Reply:
        status_code, text = 200, '{"id": "x"}'

    def fake_post(url, json, timeout, headers):
        calls.append((url, json, headers))
        return Reply()

    s = get_settings()
    for k, v in {"email_backend": "resend", "resend_api_key": "re_test", "email_from": "The Floor <no-reply@taskroom.app>"}.items():
        monkeypatch.setattr(s, k, v)
    monkeypatch.setattr(email_service.httpx, "post", fake_post)
    register(client)
    forgot(client)
    assert email_service.deliver_pending(db) == 1
    url, body, headers = calls[0]
    assert url == "https://api.resend.com/emails" and headers["Authorization"] == "Bearer re_test"
    assert headers["Idempotency-Key"].startswith("outbox-")
    assert (body["from"], body["to"], body["subject"]) == ("The Floor <no-reply@taskroom.app>", ["ada@example.com"], "Reset your password for The Floor")
    assert body["text"] and body["html"]


def test_resend_rejection_is_retried_with_the_reason(client, db, monkeypatch):
    class Reply:
        status_code, text = 403, '{"message": "The taskroom.app domain is not verified."}'

    s = get_settings()
    monkeypatch.setattr(s, "email_backend", "resend")
    monkeypatch.setattr(email_service.httpx, "post", lambda *a, **k: Reply())
    register(client)
    forgot(client)
    assert email_service.deliver_pending(db) == 0
    row = db.scalar(select(OutboxEmail))
    assert row.attempts == 1 and "not verified" in row.last_error and row.failed_at is None
