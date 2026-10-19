"""Refresh tokens: login cookie, rotation, theft detection, logout, and socket re-auth."""
import hashlib
import time
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from starlette.websockets import WebSocketDisconnect

from app.core.config import get_settings
from app.models.refresh_token import RefreshToken
from app.models.room import Room
from app.models.user import User
from app.utils.time import utcnow
from tests.conftest import CLIENT_HEADER, auth_headers, register

API = "/api/v1"


def do_login(client, email="ada@example.com", password="password123", headers=CLIENT_HEADER):
    return client.post(f"{API}/auth/login", json={"email": email, "password": password}, headers=headers)


def signed_in(client, email="ada@example.com", name="Ada"):
    register(client, email=email, name=name)
    r = do_login(client, email=email)
    assert r.status_code == 200, r.text
    return r.json()["access_token"], r.cookies.get("tr_refresh")


def refresh_with(client, raw, headers=CLIENT_HEADER):
    """Present exactly this refresh token (nothing else from the cookie jar)."""
    client.cookies.clear()
    h = dict(headers)
    if raw is not None:
        h["Cookie"] = f"tr_refresh={raw}"
    return client.post(f"{API}/auth/refresh", headers=h)


def age_use(db, raw, seconds):
    """Pretend this token was first used `seconds` ago (beyond the grace period)."""
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == hashlib.sha256(raw.encode()).hexdigest())
        .values(used_at=utcnow() - timedelta(seconds=seconds))
    )
    db.commit()


def cookie_header(r):
    return [v for k, v in r.headers.multi_items() if k.lower() == "set-cookie" and v.startswith("tr_refresh=")]


def err(r, status, code=None):
    assert r.status_code == status, r.text
    if code:
        assert r.json()["error"]["code"] == code
    return r.json()["error"]


# =========================================================== login

def test_login_body_is_unchanged_and_sets_the_cookie(client):
    register(client)
    r = do_login(client)
    assert set(r.json()) == {"access_token", "token_type", "expires_in"}
    assert r.json()["expires_in"] == get_settings().access_token_expire_minutes * 60
    (header,) = cookie_header(r)
    low = header.lower()
    for part in ("httponly", "samesite=lax", "path=/api/v1/auth", "max-age=2592000"):
        assert part in low, header
    assert "secure" not in low  # off in tests and local dev


def test_cookie_is_secure_when_configured(client, monkeypatch):
    register(client)
    monkeypatch.setattr(get_settings(), "refresh_cookie_secure", True)
    (header,) = cookie_header(do_login(client))
    assert "secure" in header.lower()


def test_login_needs_the_client_header(client):
    register(client)
    err(do_login(client, headers={}), 403, "FORBIDDEN")
    err(do_login(client, headers={"X-Taskroom-Client": "curl"}), 403)


def test_wrong_password_is_still_invalid_credentials(client):
    register(client)
    err(do_login(client, password="nope-nope"), 401, "INVALID_CREDENTIALS")


def test_tokens_are_stored_hashed(client, db):
    _, raw = signed_in(client)
    (row,) = db.scalars(select(RefreshToken)).all()
    assert row.token_hash == hashlib.sha256(raw.encode()).hexdigest() and raw not in row.token_hash


# =========================================================== refresh

def test_refresh_rotates_and_returns_me(client):
    _, raw = signed_in(client)
    r = refresh_with(client, raw)
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == get_settings().access_token_expire_minutes * 60
    assert (body["me"]["email"], body["me"]["rooms"]) == ("ada@example.com", [])
    new = r.cookies.get("tr_refresh")
    assert new and new != raw
    me = client.get(f"{API}/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200


def test_refresh_needs_the_client_header(client):
    _, raw = signed_in(client)
    err(refresh_with(client, raw, headers={}), 403, "FORBIDDEN")


@pytest.mark.parametrize("raw", [None, "garbage"])
def test_refresh_without_a_valid_cookie_is_401_and_clears_it(client, raw):
    signed_in(client)
    r = refresh_with(client, raw)
    err(r, 401, "UNAUTHENTICATED")
    (header,) = cookie_header(r)
    assert "max-age=0" in header.lower()


def test_expired_refresh_token_is_401(client, db):
    _, raw = signed_in(client)
    db.execute(update(RefreshToken).values(expires_at=utcnow() - timedelta(seconds=1)))
    db.commit()
    err(refresh_with(client, raw), 401)


def test_deleted_account_cannot_refresh(client, db):
    _, raw = signed_in(client)
    user = db.scalar(select(User))
    db.delete(user)
    db.commit()
    err(refresh_with(client, raw), 401)


# =========================================================== several tabs, lost responses, theft

def test_two_tabs_refreshing_at_once_both_succeed(client):
    _, raw = signed_in(client)
    a = refresh_with(client, raw)
    b = refresh_with(client, raw)  # the other tab, same old cookie, within the grace period
    assert a.status_code == b.status_code == 200
    assert a.cookies.get("tr_refresh") != b.cookies.get("tr_refresh")
    assert refresh_with(client, b.cookies.get("tr_refresh")).status_code == 200


def test_a_lost_response_does_not_end_the_session(client, db):
    _, raw = signed_in(client)
    lost = refresh_with(client, raw).cookies.get("tr_refresh")  # the browser never got this one
    age_use(db, raw, 600)  # ten minutes later, e.g. after the laptop slept

    r = refresh_with(client, raw)  # presents the old cookie again
    assert r.status_code == 200
    current = r.cookies.get("tr_refresh")
    assert refresh_with(client, current).status_code == 200  # session carries on

    # the cancelled replacement can only be a stolen copy: presenting it ends the session
    err(refresh_with(client, lost), 401)
    newest = db.scalar(select(RefreshToken).order_by(RefreshToken.created_at.desc()))
    assert newest.revoke_reason == "theft"


def test_reuse_after_the_replacement_was_used_ends_the_whole_session(client, db):
    _, raw = signed_in(client)
    second = refresh_with(client, raw).cookies.get("tr_refresh")
    third = refresh_with(client, second).cookies.get("tr_refresh")  # the replacement has been used
    age_use(db, raw, 600)

    err(refresh_with(client, raw), 401)  # someone replays the old token: theft
    err(refresh_with(client, third), 401)  # the real browser's newest token is dead too
    assert db.scalar(select(func.count()).select_from(RefreshToken).where(RefreshToken.revoked_at.is_(None))) == 0


def test_theft_in_one_session_leaves_other_sessions_alone(client, db):
    _, laptop = signed_in(client)
    phone = do_login(client).cookies.get("tr_refresh")
    second = refresh_with(client, laptop).cookies.get("tr_refresh")
    refresh_with(client, second)
    age_use(db, laptop, 600)
    err(refresh_with(client, laptop), 401)
    assert refresh_with(client, phone).status_code == 200


# =========================================================== logout

def test_logout_ends_this_session_and_is_safe_to_repeat(client):
    _, raw = signed_in(client)
    other = do_login(client).cookies.get("tr_refresh")

    client.cookies.clear()
    r = client.post(f"{API}/auth/logout", headers={**CLIENT_HEADER, "Cookie": f"tr_refresh={raw}"})
    assert r.status_code == 204 and "max-age=0" in cookie_header(r)[0].lower()
    err(refresh_with(client, raw), 401)
    assert refresh_with(client, other).status_code == 200  # only this browser's session

    client.cookies.clear()
    assert client.post(f"{API}/auth/logout", headers={**CLIENT_HEADER, "Cookie": f"tr_refresh={raw}"}).status_code == 204
    client.cookies.clear()
    assert client.post(f"{API}/auth/logout", headers=CLIENT_HEADER).status_code == 204  # no cookie at all
    assert client.post(f"{API}/auth/logout").status_code == 403  # header still required


def test_logout_all_ends_every_session(client):
    access, laptop = signed_in(client)
    phone = do_login(client).cookies.get("tr_refresh")
    assert client.post(f"{API}/auth/logout-all", headers=CLIENT_HEADER).status_code == 401  # needs a bearer token
    r = client.post(f"{API}/auth/logout-all", headers={**CLIENT_HEADER, "Authorization": f"Bearer {access}"})
    assert r.status_code == 204
    err(refresh_with(client, laptop), 401)
    err(refresh_with(client, phone), 401)


def test_logout_all_does_not_touch_other_users(client):
    access, _ = signed_in(client)
    _, bola = signed_in(client, email="bola@example.com", name="Bola")
    client.post(f"{API}/auth/logout-all", headers={**CLIENT_HEADER, "Authorization": f"Bearer {access}"})
    assert refresh_with(client, bola).status_code == 200


# =========================================================== retrying after a 401 is safe

def test_a_401_never_writes_anything(client, db):
    signed_in(client)
    r = client.post(f"{API}/rooms", json={"name": "Should not exist"}, headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401
    assert db.scalar(select(func.count()).select_from(Room)) == 0


# =========================================================== socket re-auth

@pytest.fixture
def lc(app):
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_socket_reauth_moves_expiry_without_reconnecting(lc):
    import jwt
    from datetime import datetime, timezone
    from app.core.security import ALGORITHM

    access, _ = signed_in(lc)
    user_id = lc.get(f"{API}/me", headers={"Authorization": f"Bearer {access}"}).json()["id"]
    short = jwt.encode({"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(seconds=3)},
                       get_settings().secret_key, algorithm=ALGORITHM)
    with lc.websocket_connect(f"{API}/ws") as ws:
        ws.send_json({"type": "auth", "token": short})
        assert ws.receive_json()["type"] == "ready"
        ws.send_json({"type": "auth", "token": access})  # after a refresh
        re = ws.receive_json()
        assert re["type"] == "reauthed" and re["expires_at"].endswith("Z")
        time.sleep(4)  # past the first token's expiry
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}  # still open


@pytest.mark.parametrize("bad", ["other_user", "garbage"])
def test_socket_reauth_with_a_bad_token_closes_4401(lc, bad):
    access, _ = signed_in(lc)
    token = signed_in(lc, email="bola@example.com", name="Bola")[0] if bad == "other_user" else "garbage"
    with lc.websocket_connect(f"{API}/ws") as ws:
        ws.send_json({"type": "auth", "token": access})
        assert ws.receive_json()["type"] == "ready"
        ws.send_json({"type": "auth", "token": token})
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
        assert e.value.code == 4401
