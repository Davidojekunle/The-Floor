"""Admins and the change log: only the owner makes or removes admins; every switch change is logged."""
import pytest
from sqlalchemy import update

from app.core.config import get_settings
from app.models.user import User
from tests.conftest import make_team

API = "/api/v1"


@pytest.fixture
def team(client, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "owner_email", "head@example.com")
    t = make_team(client)
    db.execute(update(User).where(User.email.in_(["head@example.com", "femi@example.com"])).values(is_staff=True))
    db.commit()
    return t


def test_me_says_who_is_owner(client, team):
    assert client.get(f"{API}/me", headers=team.head).json()["is_owner"] is True
    assert client.get(f"{API}/me", headers=team.femi).json()["is_owner"] is False


def test_only_the_owner_adds_and_removes_admins(client, team):
    # another admin can see the list but not change it
    assert len(client.get(f"{API}/admin/admins", headers=team.femi).json()) == 2
    assert client.post(f"{API}/admin/admins", json={"email": "tola@example.com"}, headers=team.femi).status_code == 404
    # nobody else even sees the list
    assert client.get(f"{API}/admin/admins", headers=team.tola).status_code == 404

    r = client.post(f"{API}/admin/admins", json={"email": " TOLA@example.com "}, headers=team.head)
    assert r.status_code == 200 and {p["email"] for p in r.json()} == {"head@example.com", "femi@example.com", "tola@example.com"}
    assert client.get(f"{API}/me", headers=team.tola).json()["is_staff"] is True

    tola = team.ids["tola"]
    assert client.delete(f"{API}/admin/admins/{tola}", headers=team.femi).status_code == 404
    r = client.delete(f"{API}/admin/admins/{tola}", headers=team.head)
    assert r.status_code == 200 and "tola@example.com" not in {p["email"] for p in r.json()}
    # the owner can't be removed
    assert client.delete(f"{API}/admin/admins/{team.ids['head']}", headers=team.head).status_code == 409
    # unknown email
    assert client.post(f"{API}/admin/admins", json={"email": "nobody@example.com"}, headers=team.head).status_code == 404

    log = client.get(f"{API}/admin/log", headers=team.femi).json()
    assert [e["action"] for e in log[:2]] == ["admin_removed", "admin_added"]
    assert log[0]["actor_name"] == "Ada" and log[0]["detail"]["email"] == "tola@example.com"


def test_switch_changes_are_logged_with_who_and_what(client, team):
    assert client.patch(f"{API}/admin/settings", json={"push": False}, headers=team.femi).status_code == 200
    assert client.patch(f"{API}/admin/settings", json={"push": False}, headers=team.femi).status_code == 200  # no change
    assert client.patch(f"{API}/admin/settings", json={"announcement": "Hello"}, headers=team.head).status_code == 200
    log = client.get(f"{API}/admin/log", headers=team.head).json()
    assert len(log) == 2
    assert log[0]["actor_name"] == "Ada" and log[0]["detail"] == {"key": "announcement", "old": None, "new": "Hello"}
    assert log[1]["actor_name"] == "Femi" and log[1]["detail"] == {"key": "push", "old": True, "new": False}
    assert client.get(f"{API}/admin/log", headers=team.tola).status_code == 404
