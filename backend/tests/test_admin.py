"""The staff-only admin page: who can see it, what it counts, and that it never leaks content."""
import json
import uuid

import pytest
from sqlalchemy import select, update

from app.models.task import Stage
from app.models.user import User
from scripts import staff as staff_cli
from tests.conftest import create_task, make_team, put_status, send

API = "/api/v1"


@pytest.fixture
def team(client):
    return make_team(client)


def make_staff(db, email="head@example.com"):
    db.execute(update(User).where(User.email == email).values(is_staff=True))
    db.commit()


def test_not_staff_gets_404(client, team):
    r = client.get(f"{API}/admin/stats", headers=team.head)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_needs_sign_in(client):
    assert client.get(f"{API}/admin/stats").status_code == 401


def test_me_says_who_is_staff(client, db, team):
    assert client.get(f"{API}/me", headers=team.head).json()["is_staff"] is False
    make_staff(db)
    assert client.get(f"{API}/me", headers=team.head).json()["is_staff"] is True
    assert client.get(f"{API}/me", headers=team.femi).json()["is_staff"] is False


def test_staff_can_be_set_by_the_api(client, team):
    r = client.patch(f"{API}/me", json={"is_staff": True}, headers=team.head)
    assert client.get(f"{API}/me", headers=team.head).json()["is_staff"] is False, r.text


def test_counts(client, db, team):
    make_staff(db)
    task = create_task(client, team, title="Secret launch plan")
    script, shoot = task["stages"][0], task["stages"][1]
    assert put_status(client, team, task, script, "done", team.femi).status_code == 200
    db.execute(update(Stage).where(Stage.id == uuid.UUID(shoot["id"])).values(status="blocked", blocked_reason="no camera"))
    db.commit()
    send(client, team, team.femi, body="the password is hunter2")

    r = client.get(f"{API}/admin/stats", headers=team.head)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["people"]["total"] == 3 and s["people"]["new_7d"] == 3
    assert s["people"]["active_7d"] == 3  # each signed in once
    assert s["rooms"]["total"] == 1 and s["rooms"]["active_30d"] == 1
    assert s["rooms"]["average_members"] == 3.0
    assert s["work"]["tasks_total"] == 1 and s["work"]["tasks_open"] == 1 and s["work"]["tasks_finished_7d"] == 0
    assert s["work"]["stages_done_7d"] == 1
    assert s["work"]["stages_blocked"] == 1
    assert s["activity"]["messages_7d"] == 1
    assert s["health"]["database_ok"] is True
    assert len(s["weeks"]) == 8
    assert s["weeks"][-1]["signups"] == 3 and s["weeks"][-1]["stages_done"] == 1 and s["weeks"][-1]["messages"] == 1


def test_finished_task_counts(client, db, team):
    make_staff(db)
    task = create_task(client, team, stages=[{"title": "Only stage", "tag_id": team.tags["Content Writer"]["id"]}])
    assert put_status(client, team, task, task["stages"][0], "done", team.femi).status_code == 200
    w = client.get(f"{API}/admin/stats", headers=team.head).json()["work"]
    assert w["tasks_open"] == 0 and w["tasks_finished_7d"] == 1


def test_overdue_stage_counts(client, db, team):
    make_staff(db)
    create_task(client, team, due_date="2000-01-01T00:00:00Z")
    assert client.get(f"{API}/admin/stats", headers=team.head).json()["work"]["stages_overdue"] == 1


def test_no_content_or_names_leak(client, db, team):
    make_staff(db)
    create_task(client, team, title="Secret launch plan")
    send(client, team, team.femi, body="the password is hunter2")
    raw = json.dumps(client.get(f"{API}/admin/stats", headers=team.head).json())
    for leaked in ("Secret launch plan", "hunter2", "Studio Alpha", "femi@example.com", "Femi", "Content Writer"):
        assert leaked not in raw


def test_staff_script(db, team, monkeypatch, capsys):
    from sqlalchemy.orm import sessionmaker

    monkeypatch.setattr(staff_cli, "SessionLocal", sessionmaker(bind=db.get_bind(), expire_on_commit=False))
    assert staff_cli.main(["add", "FEMI@example.com"]) == 0
    assert db.scalar(select(User.is_staff).where(User.email == "femi@example.com").execution_options(populate_existing=True))
    assert staff_cli.main(["list"]) == 0
    assert "femi@example.com" in capsys.readouterr().out
    assert staff_cli.main(["add", "nobody@example.com"]) == 1
    assert staff_cli.main(["remove", "femi@example.com"]) == 0
    db.expire_all()
    assert not db.scalar(select(User.is_staff).where(User.email == "femi@example.com"))
    assert staff_cli.main([]) == 2
