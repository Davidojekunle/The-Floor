"""Phase 6a: exactly one system message per room event, and none for private events."""
from datetime import datetime, timedelta, timezone

from tests.conftest import create_task, make_team, membership_id_for, messages, post_task, put_status

API = "/api/v1"


def events(client, team, headers=None):
    """System events, oldest first: [(type, actor, subject, body)]."""
    page = messages(client, team, headers, limit=100)
    out = []
    for m in reversed(page["items"]):
        if m["type"] == "system":
            e = m["event"]
            out.append((e["type"], e["actor"]["name"] if e["actor"] else None,
                        e["subject"]["name"] if e["subject"] else None, m["body"]))
    return out


def last(client, team):
    return events(client, team)[-1]


def test_member_joined(client):
    team = make_team(client)
    assert events(client, team) == [
        ("member_joined", "Ada", "Femi", "Femi joined the room"),
        ("member_joined", "Ada", "Tola", "Tola joined the room"),
    ]


def test_task_created_only_for_direct_creates_and_template_applies(client):
    team = make_team(client)
    create_task(client, team)
    assert last(client, team) == ("task_created", "Ada", None, "Ada created Product promo video")
    r = client.post(f"{API}/rooms/{team.room['id']}/templates", headers=team.head,
                    json={"name": "Quick", "stages": [{"title": "Do it"}]}).json()
    client.post(f"{API}/rooms/{team.room['id']}/templates/{r['id']}/apply", headers=team.head,
                json={"title": "From template", "due_date": "2099-01-01T00:00:00Z"})
    assert last(client, team)[3] == "Ada created From template"


def test_proposals_post_nothing_until_approved(client):
    team = make_team(client)
    before = len(events(client, team))
    p = post_task(client, team, team.femi, title="Femi's idea").json()
    tasks = f"{API}/rooms/{team.room['id']}/tasks/{p['id']}"
    client.post(f"{tasks}/reject", headers=team.head)
    client.post(f"{tasks}/resubmit", headers=team.femi)
    assert len(events(client, team)) == before  # submitted, rejected, resubmitted: all private

    client.post(f"{tasks}/approve", headers=team.head)
    assert last(client, team) == ("task_approved", "Ada", "Femi", "Ada approved Femi's proposal Femi's idea")
    client.post(f"{tasks}/approve", headers=team.head)  # repeat: no second message
    assert [e[0] for e in events(client, team)].count("task_approved") == 1


def test_stage_events_and_task_completed(client):
    team = make_team(client)
    task = create_task(client, team, stages=[{"title": "Script"}, {"title": "Edit"}])
    script, edit = task["stages"]

    put_status(client, team, task, script, "in_progress", team.head)  # not a milestone
    put_status(client, team, task, script, "in_progress", team.head)  # no-op
    put_status(client, team, task, script, "done", team.head)
    assert last(client, team) == ("stage_done", "Ada", None, "Ada finished Script on Product promo video")

    put_status(client, team, task, edit, "in_progress", team.head)
    put_status(client, team, task, edit, "blocked", team.head, reason="Waiting for music")
    page = messages(client, team, limit=1)
    blocked = page["items"][0]
    assert blocked["event"]["type"] == "stage_blocked" and blocked["event"]["detail"] == {"reason": "Waiting for music"}
    assert blocked["body"] == "Ada blocked Edit on Product promo video: Waiting for music"
    assert blocked["stage"]["title"] == "Edit"

    put_status(client, team, task, edit, "in_progress", team.head)
    put_status(client, team, task, edit, "done", team.head)
    assert [e[0] for e in events(client, team)][-2:] == ["stage_done", "task_completed"]  # in that order
    assert last(client, team)[3] == "Product promo video is complete"


def test_stage_reopened(client):
    team = make_team(client)
    task = create_task(client, team)
    put_status(client, team, task, task["stages"][0], "done", team.head)
    put_status(client, team, task, task["stages"][0], "in_progress", team.head)
    assert last(client, team) == ("stage_reopened", "Ada", None, "Ada reopened Script on Product promo video")


def test_stage_unlocked_early(client):
    team = make_team(client)
    task = create_task(client, team, stages=[{"title": "Script"}, {"title": "Edit"}])
    put_status(client, team, task, task["stages"][1], "todo", team.head)
    assert last(client, team) == ("stage_unlocked", "Ada", None, "Ada unlocked Edit early on Product promo video")


def test_temp_head_granted_extended_and_revoked(client):
    team = make_team(client)
    mid = membership_id_for(client, team.room["id"], team.head, team.ids["tola"])
    url = f"{API}/rooms/{team.room['id']}/members/{mid}/temp-head"
    expires = (datetime.now(timezone.utc) + timedelta(days=7)).replace(microsecond=0)
    client.put(url, json={"expires_at": expires.strftime("%Y-%m-%dT%H:%M:%SZ")}, headers=team.head)

    granted = messages(client, team, limit=1)["items"][0]
    assert granted["event"]["type"] == "temp_head_granted"
    assert (granted["event"]["actor"]["name"], granted["event"]["subject"]["name"]) == ("Ada", "Tola")
    assert granted["event"]["detail"]["expires_at"].startswith(expires.strftime("%Y-%m-%dT%H:%M"))
    assert granted["body"].startswith("Ada made Tola temporary head until ")

    client.put(url, json={"expires_at": (expires + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")}, headers=team.head)
    assert [e[0] for e in events(client, team)].count("temp_head_granted") == 2  # extending announces again

    client.delete(url, headers=team.head)
    assert last(client, team) == ("temp_head_revoked", "Ada", "Tola", "Ada ended Tola's temporary head role")
    client.delete(url, headers=team.head)  # nothing to revoke: nothing posted
    assert [e[0] for e in events(client, team)].count("temp_head_revoked") == 1


def test_a_deleted_system_message_shows_no_event(client):
    team = make_team(client)
    first = messages(client, team)["items"][-1]
    client.delete(f"{API}/rooms/{team.room['id']}/messages/{first['id']}", headers=team.head)
    gone = messages(client, team)["items"][-1]
    assert (gone["deleted"], gone["event"], gone["body"]) == (True, None, None)
