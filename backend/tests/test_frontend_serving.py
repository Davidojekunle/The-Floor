from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import mount_frontend


def site(tmp_path, monkeypatch, frontend_url):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>The Floor</title>")
    monkeypatch.setattr(get_settings(), "frontend_url", frontend_url)
    app = FastAPI()
    mount_frontend(app, tmp_path, "/api/v1")
    return app


def test_old_render_address_sends_pages_to_the_domain(tmp_path, monkeypatch):
    app = site(tmp_path, monkeypatch, "https://thefloorapp.me")
    old = TestClient(app, base_url="https://the-floor.onrender.com", follow_redirects=False)
    r = old.get("/privacy?x=1")
    assert r.status_code == 301 and r.headers["location"] == "https://thefloorapp.me/privacy?x=1"
    assert old.get("/").headers["location"] == "https://thefloorapp.me/"
    assert old.get("/api/v1/nope").status_code == 404  # the API is never redirected

    here = TestClient(app, base_url="https://thefloorapp.me", follow_redirects=False)
    assert here.get("/privacy").status_code == 200


def test_no_redirect_until_a_domain_is_set(tmp_path, monkeypatch):
    app = site(tmp_path, monkeypatch, "https://the-floor.onrender.com")  # FRONTEND_URL still the Render address
    r = TestClient(app, base_url="https://the-floor.onrender.com", follow_redirects=False).get("/privacy")
    assert r.status_code == 200
