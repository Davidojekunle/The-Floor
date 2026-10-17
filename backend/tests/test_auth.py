from datetime import timedelta

import jwt
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import ALGORITHM
from app.models.user import User
from app.utils.time import utcnow
from tests.conftest import auth_headers, login, register


# ---------- register ----------

def test_register_success(client):
    r = register(client)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "ada@example.com"
    assert body["name"] == "Ada"
    assert body["timezone"] == "Africa/Lagos"
    assert "id" in body
    assert "password" not in body and "password_hash" not in body


def test_register_stores_hash_not_password(client, db):
    register(client, password="password123")
    user = db.scalar(select(User))
    assert user.password_hash != "password123"
    assert user.password_hash.startswith("$2")  # bcrypt


def test_register_duplicate_email_is_409_case_insensitive(client):
    assert register(client, email="ada@example.com").status_code == 201
    r = register(client, email="ADA@Example.com")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CONFLICT"


def test_register_email_is_normalised(client):
    r = register(client, email="  Ada@Example.COM ")
    # EmailStr trims whitespace; we also lowercase before saving
    assert r.status_code == 201
    assert r.json()["email"] == "ada@example.com"


def test_register_invalid_email(client):
    r = register(client, email="not-an-email")
    assert r.status_code == 422
    assert "email" in r.json()["error"]["fields"]


def test_register_short_password(client):
    r = register(client, password="short")
    assert r.status_code == 422
    assert "password" in r.json()["error"]["fields"]


def test_register_password_too_long_for_bcrypt(client):
    r = register(client, password="a" * 73)
    assert r.status_code == 422
    assert "password" in r.json()["error"]["fields"]


def test_register_unknown_timezone(client):
    r = register(client, timezone="Mars/Olympus")
    assert r.status_code == 422
    fields = r.json()["error"]["fields"]
    assert fields["timezone"] == "Unknown timezone."  # no "Value error," prefix


def test_register_blank_name(client):
    r = register(client, name="   ")
    assert r.status_code == 422
    assert "name" in r.json()["error"]["fields"]


def test_register_missing_fields_lists_each(client):
    r = client.post("/api/v1/auth/register", json={})
    assert r.status_code == 422
    fields = r.json()["error"]["fields"]
    assert {"name", "email", "password"} <= set(fields)


# ---------- login ----------

def test_login_success(client):
    register(client)
    r = login(client)
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == get_settings().access_token_expire_minutes * 60
    assert body["access_token"]


def test_login_email_case_insensitive(client):
    register(client)
    assert login(client, email="ADA@example.com").status_code == 200


def test_login_wrong_password(client):
    register(client)
    r = login(client, password="wrong-password")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHENTICATED"


def test_login_unknown_email_same_error_as_wrong_password(client):
    register(client)
    wrong_pw = login(client, password="wrong-password")
    unknown = login(client, email="nobody@example.com")
    assert unknown.status_code == 401
    # must not reveal which emails exist
    assert unknown.json() == wrong_pw.json()


# ---------- /me ----------

def test_me_returns_user_and_empty_rooms(client):
    headers = auth_headers(client)
    r = client.get("/api/v1/me", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "ada@example.com"
    assert body["timezone"] == "Africa/Lagos"
    assert body["rooms"] == []
    assert "password_hash" not in body


def test_me_without_token_is_401(client):
    r = client.get("/api/v1/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHENTICATED"


def test_me_with_garbage_token_is_401(client):
    r = client.get("/api/v1/me", headers={"Authorization": "Bearer not.a.token"})
    assert r.status_code == 401


def test_me_with_wrong_scheme_is_401(client):
    headers = auth_headers(client)
    token = headers["Authorization"].split()[1]
    r = client.get("/api/v1/me", headers={"Authorization": f"Basic {token}"})
    assert r.status_code == 401


def test_me_with_expired_token_is_401(client, db):
    register(client)
    user = db.scalar(select(User))
    past = utcnow() - timedelta(hours=1)
    token = jwt.encode(
        {"sub": str(user.id), "iat": past - timedelta(hours=1), "exp": past},
        get_settings().secret_key,
        algorithm=ALGORITHM,
    )
    r = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_me_with_token_signed_by_wrong_key_is_401(client, db):
    register(client)
    user = db.scalar(select(User))
    token = jwt.encode(
        {"sub": str(user.id), "exp": utcnow() + timedelta(hours=1)},
        "some-other-secret-key-of-sufficient-length-123456",
        algorithm=ALGORITHM,
    )
    r = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_me_for_deleted_user_is_401(client, db):
    headers = auth_headers(client)
    db.delete(db.scalar(select(User)))
    db.commit()
    r = client.get("/api/v1/me", headers=headers)
    assert r.status_code == 401
