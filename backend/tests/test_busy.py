"""When every database connection is taken, people get a clear "busy, try again" instead of a 500."""
from sqlalchemy.exc import TimeoutError as PoolTimeout

from app.db.session import get_db
from tests.conftest import CLIENT_HEADER, register


def test_pool_exhausted_is_a_503_with_retry_after(app, client):
    def no_connection():
        raise PoolTimeout("QueuePool limit of size 5 overflow 10 reached")
        yield  # pragma: no cover

    app.dependency_overrides[get_db] = no_connection
    r = client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "password123"}, headers=CLIENT_HEADER)
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "SERVER_BUSY"
    assert r.headers["Retry-After"] == "5"


def test_sign_in_still_works_after_handing_the_connection_back(client):
    register(client)
    r = client.post("/api/v1/auth/login", json={"email": "ada@example.com", "password": "password123"}, headers=CLIENT_HEADER)
    assert r.status_code == 200, r.text
    assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).json()["email"] == "ada@example.com"
    bad = client.post("/api/v1/auth/login", json={"email": "ada@example.com", "password": "wrong-password"}, headers=CLIENT_HEADER)
    assert bad.status_code == 401
