"""The task assistant: staff only, asks then drafts, never trusts ids from the model, 5 per room per week."""
import uuid

import pytest
from sqlalchemy import update

from app.core.config import get_settings
from app.models.user import User
from app.services import task_assistant
from tests.conftest import make_team

API = "/api/v1"


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(get_settings(), "assistant_provider", "fake")
    task_assistant.FAKE_REPLIES.clear()
    task_assistant.FAKE_CALLS.clear()
    return task_assistant


@pytest.fixture
def team(client, db):
    t = make_team(client)
    db.execute(update(User).where(User.email == "head@example.com").values(is_staff=True))
    db.commit()
    return t


def url(team):
    return f"{API}/rooms/{team.room['id']}/assistant"


def say(client, team, text, conversation_id=None, history=(), who=None):
    body = {"messages": [*history, {"role": "user", "text": text}]}
    if conversation_id:
        body["conversation_id"] = conversation_id
    return client.post(f"{url(team)}/task-draft", json=body, headers=who or team.head)


def test_not_staff_gets_404(client, fake, team):
    assert say(client, team, "anything", who=team.femi).status_code == 404
    assert client.get(url(team), headers=team.femi).status_code == 404
    assert client.get(f"{API}/me", headers=team.femi).json()["task_assistant"] is False
    assert client.get(f"{API}/me", headers=team.head).json()["task_assistant"] is True


def test_asks_then_drafts_with_checked_ids(client, fake, team):
    femi, tola = team.ids["femi"], team.ids["tola"]
    editor = team.tags["Video Editor"]["id"]
    fake.FAKE_REPLIES.append({"kind": "questions", "message": "Who films it?", "questions": ["Who films it?"]})
    r = say(client, team, "Freshers reel: Femi writes the script by Friday, someone films, the editor edits")
    assert r.status_code == 200, r.text
    first = r.json()
    assert first["kind"] == "questions" and first["questions"] == ["Who films it?"] and first["draft"] is None
    assert first["uses_left"] == 4
    # the model saw the room's people and tags, not just the text
    system = fake.FAKE_CALLS[-1]["system"]
    assert "Femi" in system and "Video Editor" in system and femi in system

    fake.FAKE_REPLIES.append({
        "kind": "draft",
        "message": "Here's the plan. Should I fill this in?",
        "task": {
            "title": "Freshers reel",
            "due_date": "2099-01-10",
            "stages": [
                {"title": "Write the script", "assignee_id": femi, "due_date": "2099-01-02"},
                {"title": "Film", "assignee_id": tola},
                {"title": "Edit", "tag_id": editor},
                {"title": "Post", "assignee_id": str(uuid.uuid4())},  # not in the room: dropped
                {"title": "  "},  # empty: skipped
            ],
        },
    })
    history = [
        {"role": "user", "text": "Freshers reel: Femi writes the script by Friday, someone films, the editor edits"},
        {"role": "assistant", "text": first["message"]},
    ]
    r = say(client, team, "Tola films", conversation_id=first["conversation_id"], history=history)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["kind"] == "draft" and d["uses_left"] == 4  # a follow-up doesn't use another description
    stages = d["draft"]["stages"]
    assert [s["title"] for s in stages] == ["Write the script", "Film", "Edit", "Post"]
    assert stages[0]["assignee_id"] == femi and stages[0]["due_date"] == "2099-01-02"
    assert stages[1]["assignee_id"] == tola
    assert stages[2]["tag_id"] == editor and stages[2]["assignee_id"] is None
    assert stages[3]["assignee_id"] is None
    assert d["draft"]["due_date"] == "2099-01-10"


def test_bad_dates_and_missing_due_get_safe_defaults(client, fake, team):
    fake.FAKE_REPLIES.append({
        "kind": "draft", "message": "ok?",
        "task": {"title": "", "due_date": "not a date", "stages": [{"title": "Do it", "due_date": "1999-01-01"}]},
    })
    d = say(client, team, "do it").json()["draft"]
    assert d["title"] == "Do it"  # falls back to the first stage
    assert d["stages"][0]["due_date"] is None  # a past date is dropped
    assert d["due_date"] > "2000-01-01"  # 7 days from today


def test_draft_with_no_stages_becomes_a_question(client, fake, team):
    fake.FAKE_REPLIES.append({"kind": "draft", "message": "done", "task": {"title": "x", "stages": []}})
    r = say(client, team, "hmm").json()
    assert r["kind"] == "questions" and r["draft"] is None


def test_five_new_descriptions_per_room_per_week(client, fake, team):
    for i in range(5):
        fake.FAKE_REPLIES.append({"kind": "questions", "message": "?"})
        assert say(client, team, f"task {i}").status_code == 200
    r = say(client, team, "one more")
    assert r.status_code == 409 and r.json()["error"]["code"] == "ASSISTANT_LIMIT_REACHED"
    assert client.get(url(team), headers=team.head).json()["uses_left"] == 0


def test_turns_per_description_are_capped(client, fake, team, monkeypatch):
    monkeypatch.setattr(get_settings(), "assistant_max_turns", 2)
    fake.FAKE_REPLIES.extend([{"kind": "questions", "message": "?"}, {"kind": "questions", "message": "?"}])
    cid = say(client, team, "a").json()["conversation_id"]
    hist = [{"role": "user", "text": "a"}, {"role": "assistant", "text": "?"}]
    last = say(client, team, "b", conversation_id=cid, history=hist).json()
    assert last["turns_left"] == 0 and "as many questions" in last["message"]
    hist += [{"role": "user", "text": "b"}, {"role": "assistant", "text": "?"}]
    assert say(client, team, "c", conversation_id=cid, history=hist).status_code == 409


def test_someone_elses_conversation_is_refused(client, fake, team, db):
    db.execute(update(User).where(User.email == "femi@example.com").values(is_staff=True))
    db.commit()
    fake.FAKE_REPLIES.append({"kind": "questions", "message": "?"})
    cid = say(client, team, "a").json()["conversation_id"]
    hist = [{"role": "user", "text": "a"}, {"role": "assistant", "text": "?"}]
    assert say(client, team, "b", conversation_id=cid, history=hist, who=team.femi).status_code == 404


def test_model_failure_counts_nothing(client, fake, team):
    r = say(client, team, "anything")  # no fake reply queued = the model "didn't answer"
    assert r.status_code == 503 and r.json()["error"]["code"] == "ASSISTANT_UNAVAILABLE"
    assert client.get(url(team), headers=team.head).json()["uses_left"] == 5


def test_off_without_a_key(client, team, monkeypatch):
    monkeypatch.setattr(get_settings(), "assistant_provider", "anthropic")
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")
    assert client.get(f"{API}/me", headers=team.head).json()["task_assistant"] is False
    assert say(client, team, "x").status_code == 503


def test_conversation_must_end_with_the_person(client, fake, team):
    body = {"messages": [{"role": "assistant", "text": "hi"}]}
    assert client.post(f"{url(team)}/task-draft", json=body, headers=team.head).status_code == 422


def test_admin_switch_decides_who_can_use_it(client, fake, team):
    patch = lambda mode: client.patch(f"{API}/admin/settings", json={"task_assistant": mode}, headers=team.head)  # noqa: E731
    assert patch("everyone").status_code == 200
    assert client.get(f"{API}/me", headers=team.femi).json()["task_assistant"] is True
    fake.FAKE_REPLIES.append({"kind": "questions", "message": "?"})
    assert say(client, team, "hi", who=team.femi).status_code == 200  # Femi isn't staff
    assert patch("off").status_code == 200
    assert client.get(f"{API}/me", headers=team.head).json()["task_assistant"] is False
    assert say(client, team, "hi").status_code == 404
    log = client.get(f"{API}/admin/log", headers=team.head).json()
    assert log[0]["detail"] == {"key": "task_assistant", "old": "everyone", "new": "off"}
