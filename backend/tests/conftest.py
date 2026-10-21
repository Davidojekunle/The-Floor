import os

# Set before the app is imported, so Settings can load without a real .env
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://taskroom:taskroom@localhost:5432/taskroom")
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-at-least-32-bytes-long")
os.environ["BCRYPT_ROUNDS"] = "4"  # fast hashing in tests
os.environ["REFRESH_COOKIE_SECURE"] = "false"  # the test client talks plain http
os.environ["RATE_LIMIT_ENABLED"] = "false"  # switched on only by the rate-limit tests
os.environ["EMAIL_SENDER_ENABLED"] = "false"  # tests deliver the outbox by hand
os.environ["EMAIL_BACKEND"] = "console"  # never real email, whatever backend/.env says

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registers tables)
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app

# Tests run on in-memory SQLite by default. To run against Postgres instead:
#   TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/taskroom_test pytest
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "sqlite://")


@pytest.fixture
def engine():
    kwargs = {}
    if TEST_DATABASE_URL.startswith("sqlite"):
        kwargs = {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
    engine = create_engine(TEST_DATABASE_URL, **kwargs)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db(engine):
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    yield session
    session.close()


@pytest.fixture
def app(engine):
    app = create_app()
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    return app


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


# ---- helpers other test files can use ----

CLIENT_HEADER = {"X-Taskroom-Client": "web"}


def register(client, email="ada@example.com", name="Ada", password="password123", timezone="Africa/Lagos"):
    return client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": email, "password": password, "timezone": timezone},
    )


def login(client, email="ada@example.com", password="password123"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password}, headers=CLIENT_HEADER)


def auth_headers(client, email="ada@example.com", password="password123", **register_kwargs):
    """Register (if needed) + login, return an Authorization header dict."""
    register(client, email=email, password=password, **register_kwargs)
    token = login(client, email=email, password=password).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---- room helpers ----

def create_room(client, headers, name="Studio Alpha"):
    r = client.post("/api/v1/rooms", json={"name": name}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def request_join(client, headers, invite_code):
    return client.post(f"/api/v1/join/{invite_code}", headers=headers)


def approve(client, room_id, membership_id, headers):
    return client.post(f"/api/v1/rooms/{room_id}/join-requests/{membership_id}/approve", headers=headers)


def reject(client, room_id, membership_id, headers):
    return client.post(f"/api/v1/rooms/{room_id}/join-requests/{membership_id}/reject", headers=headers)


def join_and_approve(client, room, head_headers, user_headers):
    """User asks to join via the invite link; head approves. Returns the membership id."""
    r = request_join(client, user_headers, room["invite_code"])
    assert r.status_code == 201, r.text
    membership_id = r.json()["membership_id"]
    a = approve(client, room["id"], membership_id, head_headers)
    assert a.status_code == 200, a.text
    return membership_id


def user_id_of(client, headers):
    return client.get("/api/v1/me", headers=headers).json()["id"]


# ---- tag / member helpers ----

def create_tag(client, room_id, headers, name="Video Editor"):
    r = client.post(f"/api/v1/rooms/{room_id}/tags", json={"name": name}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def members_of(client, room_id, headers, **params):
    r = client.get(f"/api/v1/rooms/{room_id}/members", params=params, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def membership_id_for(client, room_id, headers, user_id):
    for m in members_of(client, room_id, headers, limit=100)["items"]:
        if m["user"]["id"] == user_id:
            return m["membership_id"]
    raise AssertionError("member not found")


# ---- task helpers ----

def make_team(client):
    """Room 'Studio Alpha' with a head (Ada) and two tagged members:
    Femi = Content Writer, Tola = Video Editor. A third tag, Videographer, has nobody yet."""
    from types import SimpleNamespace

    head = auth_headers(client, email="head@example.com", name="Ada")
    femi = auth_headers(client, email="femi@example.com", name="Femi")
    tola = auth_headers(client, email="tola@example.com", name="Tola")
    room = create_room(client, head)
    join_and_approve(client, room, head, femi)
    join_and_approve(client, room, head, tola)

    tags = {n: create_tag(client, room["id"], head, n) for n in ("Content Writer", "Videographer", "Video Editor")}
    ids = {"head": user_id_of(client, head), "femi": user_id_of(client, femi), "tola": user_id_of(client, tola)}
    for person, tag in (("femi", "Content Writer"), ("tola", "Video Editor")):
        mid = membership_id_for(client, room["id"], head, ids[person])
        r = client.patch(
            f"/api/v1/rooms/{room['id']}/members/{mid}", json={"tag_ids": [tags[tag]["id"]]}, headers=head
        )
        assert r.status_code == 200, r.text
    return SimpleNamespace(head=head, femi=femi, tola=tola, room=room, tags=tags, ids=ids)


FAR_FUTURE = "2099-10-30T17:00:00Z"


def task_body(team, **overrides):
    body = {
        "title": "Product promo video",
        "description": "30s cut for Instagram",
        "due_date": FAR_FUTURE,
        "stages": [
            {"title": "Script", "tag_id": team.tags["Content Writer"]["id"]},
            {"title": "Shoot", "tag_id": team.tags["Videographer"]["id"]},
            {"title": "Edit", "tag_id": team.tags["Video Editor"]["id"]},
        ],
    }
    body.update(overrides)
    return body


def post_task(client, team, headers=None, **overrides):
    return client.post(f"/api/v1/rooms/{team.room['id']}/tasks", json=task_body(team, **overrides), headers=headers or team.head)


def create_task(client, team, headers=None, **overrides):
    r = post_task(client, team, headers, **overrides)
    assert r.status_code == 201, r.text
    return r.json()


def stage_url(team, task, stage):
    return f"/api/v1/rooms/{team.room['id']}/tasks/{task['id']}/stages/{stage['id'] if isinstance(stage, dict) else stage}"


def put_status(client, team, task, stage, status, headers, reason=None):
    body = {"status": status}
    if reason is not None:
        body["blocked_reason"] = reason
    return client.put(stage_url(team, task, stage) + "/status", json=body, headers=headers)


def get_task(client, team, task, headers=None):
    r = client.get(f"/api/v1/rooms/{team.room['id']}/tasks/{task['id']}", headers=headers or team.head)
    assert r.status_code == 200, r.text
    return r.json()


# ---- chat helpers ----

def messages(client, team, headers=None, **params):
    r = client.get(f"/api/v1/rooms/{team.room['id']}/messages", params=params, headers=headers or team.head)
    assert r.status_code == 200, r.text
    return r.json()


def send(client, team, headers, body="Hello", **refs):
    return client.post(f"/api/v1/rooms/{team.room['id']}/messages", json={"body": body, **refs}, headers=headers)


def unread(client, headers, room_name="Studio Alpha"):
    rooms = client.get("/api/v1/me", headers=headers).json()["rooms"]
    return next(r["unread_messages"] for r in rooms if r["name"] == room_name)
