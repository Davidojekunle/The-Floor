"""L3: profile and theme, change password, change email."""
import re
import time
from datetime import timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from starlette.websockets import WebSocketDisconnect

from app.core.config import get_settings
from app.core.ratelimit import limiter
from app.core.security import ALGORITHM
from app.models.email import EmailChangeToken, OutboxEmail
from app.models.user import User
from app.utils.time import utcnow
from tests.conftest import CLIENT_HEADER, login, register

API = "/api/v1"


@pytest.fixture
def lc(app):
    """HTTP and sockets on one portal, like one server process. This is "this device"."""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def signed_in(c, **kw):
    register(c, **kw)
    return login(c, email=kw.get("email", "ada@example.com")).json()["access_token"]


def old_token(db, email="ada@example.com", seconds=10):
    """An access token issued a while ago (one from the same second as a sign-out stays valid by design)."""
    user = db.scalar(select(User).where(User.email == email))
    iat = int(utcnow().timestamp()) - seconds
    return jwt.encode({"sub": str(user.id), "iat": iat, "exp": iat + 900}, get_settings().secret_key, algorithm=ALGORITHM)


def emails(db, to=None):
    q = select(OutboxEmail).order_by(OutboxEmail.created_at)
    if to:
        q = q.where(OutboxEmail.to_address == to)
    return list(db.scalars(q))


def link_token(row, path):
    return re.search(rf"/{path}\?token=([A-Za-z0-9_\-]+)", row.text_body).group(1)


def err(r, status, code=None):
    assert r.status_code == status, r.text
    if code:
        assert r.json()["error"]["code"] == code, r.text
    return r.json()["error"]


def ws_ready(c, token):
    ws = c.websocket_connect(f"{API}/ws").__enter__()
    ws.send_json({"type": "auth", "token": token})
    assert ws.receive_json()["type"] == "ready"
    return ws


def drain(ws):
    time.sleep(0.05)
    ws.send_json({"type": "ping"})
    out = []
    while (m := ws.receive_json())["type"] != "pong":
        out.append(m)
    return out


# =========================================================== profile and theme

def test_me_has_theme_and_pending_email(client):
    token = signed_in(client)
    me = client.get(f"{API}/me", headers=bearer(token)).json()
    assert me["theme"] == "system" and me["pending_email"] is None


def test_patch_me_changes_only_what_is_sent(client):
    token = signed_in(client)
    r = client.patch(f"{API}/me", json={"theme": "dark"}, headers=bearer(token))
    assert r.status_code == 200, r.text
    assert (r.json()["theme"], r.json()["name"], r.json()["timezone"]) == ("dark", "Ada", "Africa/Lagos")
    r = client.patch(f"{API}/me", json={"name": "  Ada L.  ", "timezone": "Europe/London"}, headers=bearer(token))
    assert (r.json()["name"], r.json()["timezone"], r.json()["theme"]) == ("Ada L.", "Europe/London", "dark")
    assert "rooms" in r.json()  # the full /me body
    # the refresh response's `me` carries the theme, so the first paint can use it
    me = client.post(f"{API}/auth/refresh", headers=CLIENT_HEADER).json()["me"]
    assert me["theme"] == "dark"


@pytest.mark.parametrize("body, field", [
    ({"name": "   "}, "name"), ({"name": "x" * 101}, "name"), ({"name": None}, "name"),
    ({"timezone": "Mars/Olympus"}, "timezone"), ({"timezone": None}, "timezone"),
    ({"theme": "sepia"}, "theme"), ({"theme": None}, "theme"),
])
def test_patch_me_validation(client, body, field):
    token = signed_in(client)
    assert field in err(client.patch(f"{API}/me", json=body, headers=bearer(token)), 422)["fields"]


def test_account_changed_event_shape_and_no_event_without_change(lc):
    token = signed_in(lc)
    ws = ws_ready(lc, token)
    lc.patch(f"{API}/me", json={"theme": "light"}, headers=bearer(token))
    (event,) = drain(ws)
    assert event["type"] == "account_changed" and event["room_id"] is None
    assert set(event) <= {"type", "room_id", "at"}
    lc.patch(f"{API}/me", json={"theme": "light"}, headers=bearer(token))  # same value
    assert drain(ws) == []
    ws.__exit__(None, None, None)


# =========================================================== change password

def change_password(c, token, current="password123", new="a-new-password"):
    return c.post(f"{API}/auth/change-password", json={"current_password": current, "new_password": new},
                  headers={**CLIENT_HEADER, **bearer(token)})


def test_change_password_keeps_this_tab_and_ends_every_other_session(app, client, db):
    token = signed_in(client)
    other = TestClient(app, raise_server_exceptions=False)  # another device
    login(other)
    other_access = old_token(db)

    r = change_password(client, token)
    assert r.status_code == 200, r.text
    fresh = r.json()
    assert fresh["token_type"] == "bearer" and fresh["expires_in"] == get_settings().access_token_expire_minutes * 60

    # this tab: the fresh token works, and its refresh cookie still works
    assert client.get(f"{API}/me", headers=bearer(fresh["access_token"])).status_code == 200
    assert client.post(f"{API}/auth/refresh", headers=CLIENT_HEADER).status_code == 200
    # every other device: its access token fails now, and it can't refresh
    err(client.get(f"{API}/me", headers=bearer(other_access)), 401, "UNAUTHENTICATED")
    err(other.post(f"{API}/auth/refresh", headers=CLIENT_HEADER), 401)

    assert login(client).status_code == 401
    assert login(client, password="a-new-password").status_code == 200
    assert emails(db)[-1].subject == "Your password for The Floor was changed"


def test_change_password_closes_sockets_and_this_tab_reconnects(lc, db):
    token = signed_in(lc)
    with lc.websocket_connect(f"{API}/ws") as ws:
        ws.send_json({"type": "auth", "token": token})
        assert ws.receive_json()["type"] == "ready"
        fresh = change_password(lc, token).json()["access_token"]
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
        assert e.value.code == 4401
    with lc.websocket_connect(f"{API}/ws") as ws:
        ws.send_json({"type": "auth", "token": fresh})  # the same-second token is accepted (inclusive check)
        assert ws.receive_json()["type"] == "ready"


def test_change_password_without_a_cookie_still_works(app, db):
    c = TestClient(app, raise_server_exceptions=False)
    token = signed_in(c)
    c.cookies.clear()
    r = change_password(c, token)
    assert r.status_code == 200
    assert c.get(f"{API}/me", headers=bearer(r.json()["access_token"])).status_code == 200


def test_change_password_errors(client):
    token = signed_in(client)
    e = err(change_password(client, token, current="wrong-password"), 401, "INVALID_CREDENTIALS")
    assert "current_password" in e["fields"]
    assert "new_password" in err(change_password(client, token, new="password123"), 422)["fields"]
    assert "new_password" in err(change_password(client, token, new="short"), 422)["fields"]
    err(client.post(f"{API}/auth/change-password", json={"current_password": "password123", "new_password": "a-new-password"},
                    headers=bearer(token)), 403)  # no client header
    assert login(client).status_code == 200  # nothing changed


# =========================================================== change email

def change_email(c, token, new="ada.new@example.com", password="password123"):
    return c.post(f"{API}/auth/change-email", json={"new_email": new, "current_password": password},
                  headers={**CLIENT_HEADER, **bearer(token)})


def confirm(c, raw, password="password123"):
    return c.post(f"{API}/auth/confirm-email", json={"token": raw, "current_password": password}, headers=CLIENT_HEADER)


def test_request_sends_a_confirm_link_and_a_notice_with_cancel(client, db):
    token = signed_in(client)
    r = change_email(client, token, new="  Ada.New@Example.com ")
    assert r.status_code == 202, r.text
    (to_new,) = emails(db, "ada.new@example.com")
    (to_old,) = emails(db, "ada@example.com")
    assert "http://localhost:5173/confirm-email?token=" in to_new.text_body
    assert "http://localhost:5173/cancel-email-change?token=" in to_old.text_body
    assert "ada.new@example.com" in to_old.text_body
    me = client.get(f"{API}/me", headers=bearer(token)).json()
    assert (me["email"], me["pending_email"]) == ("ada@example.com", "ada.new@example.com")
    assert login(client).status_code == 200  # still the current address until confirmed
    assert login(client, email="ada.new@example.com").status_code == 401


def test_confirm_needs_the_password_so_the_link_alone_cant_take_the_account(app, client, db):
    token = signed_in(client)
    change_email(client, token)
    raw = link_token(emails(db, "ada.new@example.com")[0], "confirm-email")
    stranger = TestClient(app, raise_server_exceptions=False)  # whoever owns the (maybe mistyped) address

    assert "current_password" in err(confirm(stranger, raw, "guess-guess"), 401, "INVALID_CREDENTIALS")["fields"]
    assert client.get(f"{API}/me", headers=bearer(token)).json()["email"] == "ada@example.com"

    assert confirm(stranger, raw).status_code == 204  # the right password, on any device
    me = client.get(f"{API}/me", headers=bearer(token))  # sessions stay signed in
    assert me.status_code == 200
    assert (me.json()["email"], me.json()["pending_email"]) == ("ada.new@example.com", None)
    assert login(client, email="ada.new@example.com").status_code == 200
    assert login(client).status_code == 401
    assert emails(db, "ada@example.com")[-1].subject == "Your email for The Floor was changed"
    err(confirm(stranger, raw), 400, "EMAIL_TOKEN_INVALID")  # single use


def test_change_email_errors(client):
    token = signed_in(client)
    register(client, email="taken@example.com", name="Bisi")
    assert "current_password" in err(change_email(client, token, password="wrong-password"), 401, "INVALID_CREDENTIALS")["fields"]
    assert "new_email" in err(change_email(client, token, new="Taken@example.com"), 409, "CONFLICT")["fields"]
    assert "new_email" in err(change_email(client, token, new="ADA@example.com"), 422)["fields"]
    assert "new_email" in err(change_email(client, token, new="not-an-email"), 422)["fields"]
    assert client.get(f"{API}/me", headers=bearer(token)).json()["pending_email"] is None


def test_address_taken_between_request_and_confirm(client, db):
    token = signed_in(client)
    change_email(client, token)
    raw = link_token(emails(db, "ada.new@example.com")[0], "confirm-email")
    register(client, email="ada.new@example.com", name="Someone")
    assert "new_email" in err(confirm(client, raw), 409, "CONFLICT")["fields"]


def test_a_new_request_replaces_the_pending_one(client, db):
    token = signed_in(client)
    change_email(client, token, new="first@example.com")
    change_email(client, token, new="second@example.com")
    first = link_token(emails(db, "first@example.com")[0], "confirm-email")
    err(confirm(client, first), 400, "EMAIL_TOKEN_INVALID")
    assert client.get(f"{API}/me", headers=bearer(token)).json()["pending_email"] == "second@example.com"


def test_confirm_link_expires_after_24_hours(client, db):
    token = signed_in(client)
    change_email(client, token)
    row = db.scalar(select(EmailChangeToken))
    assert row.expires_at - row.created_at == timedelta(hours=24)
    raw = link_token(emails(db, "ada.new@example.com")[0], "confirm-email")
    db.execute(update(EmailChangeToken).values(expires_at=utcnow() - timedelta(seconds=1)))
    db.commit()
    err(confirm(client, raw), 400, "EMAIL_TOKEN_INVALID")
    assert client.get(f"{API}/me", headers=bearer(token)).json()["pending_email"] is None


def test_cancel_from_the_account_page(client, db):
    token = signed_in(client)
    change_email(client, token)
    raw = link_token(emails(db, "ada.new@example.com")[0], "confirm-email")
    cancel = lambda: client.delete(f"{API}/auth/change-email", headers={**CLIENT_HEADER, **bearer(token)})
    assert cancel().status_code == 204
    assert cancel().status_code == 204  # safe to repeat
    assert client.get(f"{API}/me", headers=bearer(token)).json()["pending_email"] is None
    err(confirm(client, raw), 400, "EMAIL_TOKEN_INVALID")


def test_cancel_by_the_link_sent_to_the_old_address(app, client, db):
    token = signed_in(client)
    change_email(client, token)
    confirm_raw = link_token(emails(db, "ada.new@example.com")[0], "confirm-email")
    cancel_raw = link_token(emails(db, "ada@example.com")[0], "cancel-email-change")
    anyone = TestClient(app, raise_server_exceptions=False)  # no login needed
    by_link = lambda raw: anyone.post(f"{API}/auth/cancel-email-change", json={"token": raw}, headers=CLIENT_HEADER)

    assert by_link(cancel_raw).status_code == 204
    err(confirm(client, confirm_raw), 400, "EMAIL_TOKEN_INVALID")
    err(by_link(cancel_raw), 400, "EMAIL_TOKEN_INVALID")
    err(by_link("garbage"), 400, "EMAIL_TOKEN_INVALID")
    err(by_link(confirm_raw), 400, "EMAIL_TOKEN_INVALID")  # the two links aren't interchangeable


def test_cancel_link_is_dead_once_the_change_went_through(client, db):
    token = signed_in(client)
    change_email(client, token)
    confirm(client, link_token(emails(db, "ada.new@example.com")[0], "confirm-email"))
    cancel_raw = link_token(emails(db, "ada@example.com")[0], "cancel-email-change")
    err(client.post(f"{API}/auth/cancel-email-change", json={"token": cancel_raw}, headers=CLIENT_HEADER),
        400, "EMAIL_TOKEN_INVALID")


def test_email_change_steps_tell_other_tabs(lc, db):
    token = signed_in(lc)
    ws = ws_ready(lc, token)
    change_email(lc, token)
    assert [m["type"] for m in drain(ws)] == ["account_changed"]
    confirm(lc, link_token(emails(db, "ada.new@example.com")[0], "confirm-email"))
    assert [m["type"] for m in drain(ws)] == ["account_changed"]
    ws.__exit__(None, None, None)


def test_tokens_are_stored_hashed(client, db):
    token = signed_in(client)
    change_email(client, token)
    raw = link_token(emails(db, "ada.new@example.com")[0], "confirm-email")
    row = db.scalar(select(EmailChangeToken))
    assert raw not in (row.token_hash, row.cancel_hash) and len(row.token_hash) == 64


# =========================================================== rate limits

@pytest.fixture
def limits_on(monkeypatch):
    limiter.reset()
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)
    yield
    limiter.reset()


def test_change_password_is_limited_to_5_an_hour(client, limits_on):
    token = signed_in(client)
    for _ in range(5):
        change_password(client, token, current="wrong-password")
    r = change_password(client, token)
    err(r, 429, "RATE_LIMITED")
    assert int(r.headers["Retry-After"]) > 0


def test_change_email_is_limited_to_5_an_hour(client, limits_on):
    token = signed_in(client)
    for _ in range(5):
        change_email(client, token, password="wrong-password")
    err(change_email(client, token), 429, "RATE_LIMITED")


def test_confirm_email_password_guessing_is_limited(client, db, limits_on):
    token = signed_in(client)
    change_email(client, token)
    raw = link_token(emails(db, "ada.new@example.com")[0], "confirm-email")
    for _ in range(5):
        confirm(client, raw, "guess-guess")
    err(confirm(client, raw), 429, "RATE_LIMITED")
