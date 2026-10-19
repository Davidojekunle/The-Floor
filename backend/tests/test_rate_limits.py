"""L2: rate limits. Off in every other test file; switched on here."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.config import get_settings
from app.core.ratelimit import client_ip, limiter
from tests.conftest import CLIENT_HEADER, auth_headers, create_room, make_team, register, request_join

API = "/api/v1"


@pytest.fixture(autouse=True)
def limits_on(monkeypatch):
    limiter.reset()
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)
    yield
    limiter.reset()


def login(client, email, password="password123", headers=None):
    return client.post(f"{API}/auth/login", json={"email": email, "password": password}, headers=headers or CLIENT_HEADER)


def assert_429(r):
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "RATE_LIMITED"
    assert int(r.headers["Retry-After"]) >= 1


# =========================================================== login

def test_login_is_limited_per_email(client):
    register(client)
    for _ in range(5):
        login(client, "ada@example.com", "wrong-password")
    assert_429(login(client, "ada@example.com"))  # even with the right password, for now
    assert login(client, "other@example.com").status_code == 401  # other emails unaffected


def test_unknown_emails_are_limited_the_same_way(client):
    for _ in range(5):
        login(client, "nobody@example.com")
    assert_429(login(client, "nobody@example.com"))  # a 429 doesn't reveal whether the account exists


def test_a_whole_class_behind_one_ip_can_register_and_log_in(client):
    for i in range(30):
        email = f"student{i}@unilag.edu.ng"
        assert register(client, email=email, name=f"Student {i}").status_code == 201
        assert login(client, email).status_code == 200


def test_login_flood_guard_per_ip(client):
    for i in range(100):
        login(client, f"spray{i}@example.com")
    assert_429(login(client, "spray-last@example.com"))


# =========================================================== register

def test_register_is_limited_per_email(client):
    assert register(client).status_code == 201
    register(client)
    register(client)
    assert_429(register(client))


# =========================================================== refresh

def test_refresh_is_limited_per_session(client):
    register(client)
    login(client, "ada@example.com")
    for _ in range(10):
        assert client.post(f"{API}/auth/refresh", headers=CLIENT_HEADER).status_code == 200
    assert_429(client.post(f"{API}/auth/refresh", headers=CLIENT_HEADER))


# =========================================================== in the app

def test_join_requests_are_limited_per_user(client):
    joiner = auth_headers(client, email="joiner@example.com", name="Joiner")
    codes = []
    for i in range(11):
        head = auth_headers(client, email=f"head{i}@example.com", name=f"Head {i}")
        codes.append(create_room(client, head, f"Room {i}")["invite_code"])
    for code in codes[:10]:
        assert request_join(client, joiner, code).status_code == 201
    assert_429(request_join(client, joiner, codes[10]))


def test_chat_is_limited_per_user_per_room(client):
    team = make_team(client)
    room = f"{API}/rooms/{team.room['id']}/messages"
    for i in range(30):
        assert client.post(room, json={"body": f"m{i}"}, headers=team.femi).status_code == 201
    assert_429(client.post(room, json={"body": "one too many"}, headers=team.femi))
    assert client.post(room, json={"body": "someone else"}, headers=team.tola).status_code == 201


def test_everything_else_has_a_per_user_safety_net(client):
    headers = auth_headers(client)
    limiter.reset()  # signing up and in counted too
    for _ in range(300):
        assert client.get(f"{API}/me", headers=headers).status_code == 200
    assert_429(client.get(f"{API}/me", headers=headers))


def test_retry_after_is_readable_by_the_browser(client):
    r = client.get(f"{API}/health", headers={"Origin": "http://localhost:5173"})
    assert "retry-after" in r.headers.get("access-control-expose-headers", "").lower()


# =========================================================== websocket

def test_websocket_connects_are_limited_per_user(app):
    with TestClient(app, raise_server_exceptions=False) as lc:
        headers = auth_headers(lc)
        token = headers["Authorization"].split()[1]
        for _ in range(10):
            with lc.websocket_connect(f"{API}/ws") as ws:
                ws.send_json({"type": "auth", "token": token})
                assert ws.receive_json()["type"] == "ready"
        with lc.websocket_connect(f"{API}/ws") as ws:
            ws.send_json({"type": "auth", "token": token})
            with pytest.raises(WebSocketDisconnect) as e:
                ws.receive_json()
            assert e.value.code == 4429


# =========================================================== client IP

def fake(peer, xff=None):
    return SimpleNamespace(client=SimpleNamespace(host=peer), headers={"x-forwarded-for": xff} if xff else {})


def test_client_ip_ignores_forwarded_headers_from_strangers(monkeypatch):
    monkeypatch.setattr(get_settings(), "trusted_proxies", "10.0.0.1")
    assert client_ip(fake("203.0.113.9", "1.2.3.4")) == "203.0.113.9"  # spoofed header, not from our proxy


def test_client_ip_trusts_our_proxy(monkeypatch):
    monkeypatch.setattr(get_settings(), "trusted_proxies", "10.0.0.1,10.0.0.2")
    assert client_ip(fake("10.0.0.1", "198.51.100.7")) == "198.51.100.7"
    # a client that sends its own fake header: the hop our proxy saw is the real one
    assert client_ip(fake("10.0.0.1", "6.6.6.6, 198.51.100.7, 10.0.0.2")) == "198.51.100.7"


def test_client_ip_trusts_proxy_ranges(monkeypatch):
    monkeypatch.setattr(get_settings(), "trusted_proxies", "10.0.0.0/8")
    assert client_ip(fake("10.214.3.9", "198.51.100.7, 10.1.2.3")) == "198.51.100.7"
    assert client_ip(fake("203.0.113.9", "1.2.3.4")) == "203.0.113.9"  # outside the range: header ignored
