from sqlalchemy import select

from app.core.ratelimit import limiter
from app.models.email import OutboxEmail
from tests.conftest import auth_headers

URL = "/api/v1/feedback"


def test_feedback_is_emailed_to_support(client, db):
    h = auth_headers(client, email="ada@example.com", name="Ada")
    r = client.post(URL, json={"kind": "problem", "message": "The calendar skips a day\nin October.", "page": "/rooms/x/calendar"},
                    headers={**h, "User-Agent": "TestBrowser/1.0"})
    assert r.status_code == 204, r.text
    (e,) = db.scalars(select(OutboxEmail).where(OutboxEmail.category == "feedback")).all()
    assert e.to_address == "support@thefloorapp.me"
    assert e.subject == "[Problem] The calendar skips a day in October."
    assert e.headers == {"Reply-To": "ada@example.com"}
    for part in ("The calendar skips a day", "Ada <ada@example.com>", "/rooms/x/calendar", "TestBrowser/1.0"):
        assert part in e.text_body


def test_feedback_needs_a_message_and_a_session(client):
    h = auth_headers(client)
    assert client.post(URL, json={"message": "   "}, headers=h).status_code == 422
    assert client.post(URL, json={"kind": "rant", "message": "hi"}, headers=h).status_code == 422
    assert client.post(URL, json={"message": "hi"}).status_code == 401


def test_feedback_is_rate_limited(client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)
    limiter.reset()
    h = auth_headers(client)
    for _ in range(10):
        assert client.post(URL, json={"message": "idea"}, headers=h).status_code == 204
    assert client.post(URL, json={"message": "one more"}, headers=h).status_code == 429
    limiter.reset()
