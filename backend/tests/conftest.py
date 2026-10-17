import os

# Set before the app is imported, so Settings can load without a real .env
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://taskroom:taskroom@localhost:5432/taskroom")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ["BCRYPT_ROUNDS"] = "4"  # fast hashing in tests

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

def register(client, email="ada@example.com", name="Ada", password="password123", timezone="Africa/Lagos"):
    return client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": email, "password": password, "timezone": timezone},
    )


def login(client, email="ada@example.com", password="password123"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


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
