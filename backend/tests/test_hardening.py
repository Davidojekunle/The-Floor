"""Security headers, compression, HEAD for monitors, and the production-only bits of serving the site."""
from fastapi.testclient import TestClient

from app.core.config import get_settings

API = "/api/v1"


def test_security_headers_on_api_responses(client):
    r = client.get(f"{API}/health")
    csp = r.headers["content-security-policy"]
    assert "default-src 'self'" in csp and "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert "'unsafe-eval'" not in csp and "script-src 'self' 'unsafe-inline'" not in csp
    assert "https://www.youtube-nocookie.com" in csp  # result players may be framed
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "strict-transport-security" not in r.headers  # plain http in tests: HSTS only over https


def test_hsts_over_https(app):
    with TestClient(app, base_url="https://testserver") as c:
        assert "max-age=31536000" in c.get(f"{API}/health").headers["strict-transport-security"]


def test_large_responses_are_compressed(client):
    from tests.conftest import auth_headers, create_room

    head = auth_headers(client)
    room = create_room(client, head)
    for i in range(40):
        client.post(f"{API}/rooms/{room['id']}/messages", json={"body": f"message number {i} " * 5}, headers=head)
    r = client.get(f"{API}/rooms/{room['id']}/messages", headers={**head, "Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") == "gzip"


def test_head_on_health_for_uptime_monitors(client):
    assert client.head(f"{API}/health").status_code == 200


def test_docs_on_locally(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_production_hides_docs_and_serves_the_site(tmp_path, monkeypatch, engine):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>The Floor</title>")
    (tmp_path / "robots.txt").write_text("User-agent: *")
    monkeypatch.setenv("FRONTEND_DIST", str(tmp_path))
    get_settings.cache_clear()
    try:
        from app.main import create_app

        with TestClient(create_app()) as c:
            assert c.get("/docs").status_code != 200 or "swagger" not in c.get("/docs").text.lower()
            assert c.get("/openapi.json").headers["content-type"].startswith("text/html")  # the page, not the schema
            assert c.head("/").status_code == 200  # monitors and link previews use HEAD
            assert c.get("/some/page").text.startswith("<!doctype html>")
            assert c.get("/robots.txt").text == "User-agent: *"
            assert c.get(f"{API}/nope").json()["error"]["code"] == "NOT_FOUND"
            assert "content-security-policy" in c.get("/").headers
    finally:
        monkeypatch.delenv("FRONTEND_DIST")
        get_settings.cache_clear()
