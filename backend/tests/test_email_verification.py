import re
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from app.models.email import OutboxEmail
from app.models.user import User
from app.services import account_service, notification_email
from app.utils.time import utcnow
from tests.conftest import CLIENT_HEADER, auth_headers, create_room, request_join

API = "/api/v1"
SUBJECT = "Confirm your email for The Floor"

REAL_SEND = account_service.send_verification


@pytest.fixture(autouse=True)
def confirmation_emails_on(monkeypatch, no_confirmation_emails):
    monkeypatch.setattr(account_service, "send_verification", REAL_SEND)


def link_token(db, to):
    mail = db.scalars(select(OutboxEmail).where(OutboxEmail.to_address == to, OutboxEmail.subject == SUBJECT)
                      .order_by(OutboxEmail.created_at.desc())).first()
    assert mail is not None
    return re.search(r"/verify-email\?token=(\S+)", mail.text_body).group(1)


def verify(client, token):
    return client.post(f"{API}/auth/verify-email", json={"token": token}, headers=CLIENT_HEADER)


def me(client, h):
    return client.get(f"{API}/me", headers=h).json()


def test_signing_up_sends_a_link_that_confirms_the_address(client, db):
    h = auth_headers(client, email="ada@example.com", name="Ada")
    assert me(client, h)["email_verified"] is False
    token = link_token(db, "ada@example.com")
    assert verify(client, token).status_code == 204
    assert me(client, h)["email_verified"] is True
    assert verify(client, token).status_code == 204  # opening it twice is fine


def test_bad_links_are_refused(client, db):
    auth_headers(client, email="ada@example.com", name="Ada")
    token = link_token(db, "ada@example.com")
    assert verify(client, token[:-3] + "abc").json()["error"]["code"] == "EMAIL_TOKEN_INVALID"
    assert verify(client, "nonsense").status_code == 400


def test_a_link_for_an_old_address_proves_nothing(client, db):
    h = auth_headers(client, email="ada@example.com", name="Ada")
    token = link_token(db, "ada@example.com")
    db.execute(update(User).where(User.email == "ada@example.com").values(email="new@example.com"))
    db.commit()
    assert verify(client, token).status_code == 400
    assert me(client, h)["email_verified"] is False


def test_resend(client, db):
    h = auth_headers(client, email="ada@example.com", name="Ada")
    count = lambda: len(db.scalars(select(OutboxEmail).where(OutboxEmail.subject == SUBJECT)).all())  # noqa: E731
    assert client.post(f"{API}/auth/verify-email/resend", headers={**h, **CLIENT_HEADER}).status_code == 202
    assert count() == 2
    verify(client, link_token(db, "ada@example.com"))
    client.post(f"{API}/auth/verify-email/resend", headers={**h, **CLIENT_HEADER})
    assert count() == 2  # already confirmed: nothing more is sent


def test_a_password_reset_link_also_confirms(client, db):
    auth_headers(client, email="ada@example.com", name="Ada")
    client.post(f"{API}/auth/forgot-password", json={"email": "ada@example.com"}, headers=CLIENT_HEADER)
    mail = db.scalars(select(OutboxEmail).where(OutboxEmail.to_address == "ada@example.com",
                                                OutboxEmail.subject != SUBJECT)).first()
    token = re.search(r"token=(\S+)", mail.text_body).group(1)
    r = client.post(f"{API}/auth/reset-password", json={"token": token, "new_password": "brandnew123"},
                    headers=CLIENT_HEADER)
    assert r.status_code == 204, r.text
    h = auth_headers(client, email="ada@example.com", password="brandnew123")
    assert me(client, h)["email_verified"] is True


@pytest.fixture
def new_accounts(monkeypatch):
    """Accounts made after confirmation started: no notification emails until confirmed."""
    monkeypatch.setattr(account_service, "VERIFICATION_SINCE", datetime(2000, 1, 1, tzinfo=timezone.utc))


def notification_emails(db, to):
    return db.scalars(select(OutboxEmail).where(OutboxEmail.to_address == to, OutboxEmail.category != "security")).all()


def test_new_unconfirmed_accounts_get_no_notification_emails(client, db, new_accounts):
    head = auth_headers(client, email="head@example.com", name="Ada")
    room = create_room(client, head)
    bisi = auth_headers(client, email="bisi@example.com", name="Bisi")
    request_join(client, bisi, room["invite_code"])  # the head would normally be emailed about this
    notification_email.flush_due(db, utcnow() + timedelta(hours=1))
    assert notification_emails(db, "head@example.com") == []

    verify(client, link_token(db, "head@example.com"))
    tola = auth_headers(client, email="tola@example.com", name="Tola")
    request_join(client, tola, room["invite_code"])
    notification_email.flush_due(db, utcnow() + timedelta(hours=1))
    assert len(notification_emails(db, "head@example.com")) == 1
