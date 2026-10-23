from datetime import timedelta

from sqlalchemy import select, update

from app.models.email import OutboxEmail
from app.models.room import RoomInvite
from tests.conftest import auth_headers, create_room, join_and_approve, request_join, verify

API = "/api/v1"


def invite(client, room, headers, *emails):
    return client.post(f"{API}/rooms/{room['id']}/invite/email", json={"emails": list(emails)}, headers=headers)


def test_invited_person_is_let_straight_in(client, db):
    head = auth_headers(client, email="head@example.com", name="Ada")
    room = create_room(client, head)
    r = invite(client, room, head, "Bisi@Example.com")
    assert r.status_code == 200, r.text
    assert r.json() == {"invited": ["bisi@example.com"], "already_members": []}

    (mail,) = db.scalars(select(OutboxEmail).where(OutboxEmail.category == "invite")).all()
    assert mail.to_address == "bisi@example.com" and mail.subject == "Ada invited you to Studio Alpha on The Floor"
    assert f"/join/{room['invite_code']}" in mail.text_body and mail.headers == {"Reply-To": "head@example.com"}

    bisi = auth_headers(client, email="bisi@example.com", name="Bisi")
    verify(db, "bisi@example.com")
    preview = client.get(f"{API}/join/{room['invite_code']}", headers=bisi).json()
    assert preview["invited"] is True
    joined = request_join(client, bisi, room["invite_code"])
    assert joined.status_code == 201 and joined.json()["status"] == "active"
    assert client.get(f"{API}/rooms/{room['id']}", headers=bisi).status_code == 200  # in, no approval
    assert client.get(f"{API}/rooms/{room['id']}/join-requests", headers=head).json()["items"] == []


def test_someone_else_with_the_link_still_asks(client):
    head = auth_headers(client, email="head@example.com", name="Ada")
    room = create_room(client, head)
    invite(client, room, head, "bisi@example.com")
    tola = auth_headers(client, email="tola@example.com", name="Tola")
    assert client.get(f"{API}/join/{room['invite_code']}", headers=tola).json()["invited"] is False
    assert request_join(client, tola, room["invite_code"]).json()["status"] == "pending"


def test_an_invite_works_once_and_expires(client, db):
    head = auth_headers(client, email="head@example.com", name="Ada")
    room = create_room(client, head)
    invite(client, room, head, "bisi@example.com", "tola@example.com")
    db.execute(update(RoomInvite).where(RoomInvite.email == "tola@example.com")
               .values(expires_at=RoomInvite.created_at - timedelta(days=1)))
    db.commit()
    tola = auth_headers(client, email="tola@example.com", name="Tola")
    verify(db, "tola@example.com")
    assert request_join(client, tola, room["invite_code"]).json()["status"] == "pending"  # expired: asks as usual

    bisi = auth_headers(client, email="bisi@example.com", name="Bisi")
    verify(db, "bisi@example.com")
    request_join(client, bisi, room["invite_code"])
    mid = client.get(f"{API}/rooms/{room['id']}/members", headers=head).json()["items"]
    bisi_m = next(m for m in mid if m["user"]["name"] == "Bisi")
    client.delete(f"{API}/rooms/{room['id']}/members/{bisi_m['membership_id']}", headers=head)
    assert request_join(client, bisi, room["invite_code"]).json()["status"] == "pending"  # used up: asks again


def test_members_are_skipped_and_only_heads_invite(client):
    head = auth_headers(client, email="head@example.com", name="Ada")
    room = create_room(client, head)
    bisi = auth_headers(client, email="bisi@example.com", name="Bisi")
    join_and_approve(client, room, head, bisi)
    r = invite(client, room, head, "bisi@example.com", "new@example.com", "new@example.com")
    assert r.json() == {"invited": ["new@example.com"], "already_members": ["bisi@example.com"]}
    assert invite(client, room, bisi, "x@example.com").status_code == 403
    assert invite(client, room, head, "not-an-email").status_code == 422


def test_an_unconfirmed_address_still_asks(client):
    """Otherwise anyone could sign up as the invitee and walk in."""
    head = auth_headers(client, email="head@example.com", name="Ada")
    room = create_room(client, head)
    invite(client, room, head, "bisi@example.com")
    bisi = auth_headers(client, email="bisi@example.com", name="Bisi")  # not confirmed
    assert client.get(f"{API}/join/{room['invite_code']}", headers=bisi).json()["invited"] is False
    assert request_join(client, bisi, room["invite_code"]).json()["status"] == "pending"
