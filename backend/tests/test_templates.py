import uuid

from tests.conftest import (
    FAR_FUTURE, auth_headers, create_room, create_tag, create_task, get_task, make_team, put_status,
)

API = "/api/v1"


def url(team, template=None):
    base = f"{API}/rooms/{team.room['id']}/templates"
    return base if template is None else f"{base}/{template['id'] if isinstance(template, dict) else template}"


def video_shoot(team, **overrides):
    body = {
        "name": "Video shoot",
        "stages": [
            {"title": "Script", "tag_id": team.tags["Content Writer"]["id"]},
            {"title": "Shoot", "tag_id": team.tags["Videographer"]["id"]},
            {"title": "Edit", "tag_id": team.tags["Video Editor"]["id"]},
        ],
    }
    body.update(overrides)
    return body


def create(client, team, headers=None, **overrides):
    r = client.post(url(team), json=video_shoot(team, **overrides), headers=headers or team.head)
    assert r.status_code == 201, r.text
    return r.json()


def err(r, status, code=None):
    assert r.status_code == status, r.text
    if code:
        assert r.json()["error"]["code"] == code
    return r.json()["error"]


# ---------- create ----------

def test_create_template_shape(client):
    team = make_team(client)
    t = create(client, team, name="  Video   shoot ")
    assert t["name"] == "Video shoot"
    assert set(t) == {"id", "name", "stages"}
    assert [(s["position"], s["title"], s["tag"]["name"], s["parallel_with_previous"]) for s in t["stages"]] == [
        (1, "Script", "Content Writer", False),
        (2, "Shoot", "Videographer", False),
        (3, "Edit", "Video Editor", False),
    ]


def test_template_stages_can_be_parallel_and_tag_less(client):
    team = make_team(client)
    t = create(client, team, stages=[{"title": "Shoot"}, {"title": "Graphics"}, {"title": "Music", "parallel_with_previous": True}])
    assert [s["parallel_with_previous"] for s in t["stages"]] == [False, False, True]
    assert all(s["tag"] is None for s in t["stages"])


def test_duplicate_name_is_409_ignoring_case_and_points_at_the_field(client):
    team = make_team(client)
    create(client, team)
    e = err(client.post(url(team), json=video_shoot(team, name="VIDEO SHOOT"), headers=team.head), 409, "CONFLICT")
    assert "name" in e["fields"]


def test_same_name_is_fine_in_another_room(client):
    team = make_team(client)
    create(client, team)
    other_head = auth_headers(client, email="other@example.com", name="Other")
    other_room = create_room(client, other_head, "Other room")
    r = client.post(f"{API}/rooms/{other_room['id']}/templates", json={"name": "Video shoot", "stages": [{"title": "S"}]}, headers=other_head)
    assert r.status_code == 201


def test_create_validation(client):
    team = make_team(client)
    post = lambda **o: client.post(url(team), json=video_shoot(team, **o), headers=team.head)  # noqa: E731
    assert "name" in err(post(name="   "), 422)["fields"]
    assert "stages" in err(post(stages=[]), 422)["fields"]
    assert "stages" in err(post(stages=[{"title": f"S{i}"} for i in range(31)]), 422)["fields"]
    assert "stages.1.title" in err(post(stages=[{"title": "A"}, {"title": " "}]), 422)["fields"]
    assert "stages.0.parallel_with_previous" in err(post(stages=[{"title": "A", "parallel_with_previous": True}]), 422)["fields"]
    assert "stages.0.tag_id" in err(post(stages=[{"title": "A", "tag_id": str(uuid.uuid4())}]), 422)["fields"]


def test_tag_from_another_room_is_rejected(client):
    team = make_team(client)
    other_head = auth_headers(client, email="other@example.com", name="Other")
    other_room = create_room(client, other_head, "Other room")
    foreign = create_tag(client, other_room["id"], other_head, "Foreign")
    r = client.post(url(team), json={"name": "X", "stages": [{"title": "A"}, {"title": "B", "tag_id": foreign["id"]}]}, headers=team.head)
    assert "stages.1.tag_id" in err(r, 422)["fields"]


# ---------- read ----------

def test_members_list_templates_sorted_by_name(client):
    team = make_team(client)
    create(client, team, name="video shoot")
    create(client, team, name="Article")
    create(client, team, name="Podcast")
    page = client.get(url(team), headers=team.femi).json()
    assert [t["name"] for t in page["items"]] == ["Article", "Podcast", "video shoot"]
    assert page["total"] == 3 and page["limit"] == 100  # dropdown-friendly default


def test_get_one_and_isolation(client):
    team = make_team(client)
    t = create(client, team)
    assert client.get(url(team, t), headers=team.femi).json()["name"] == "Video shoot"
    assert client.get(url(team, uuid.uuid4()), headers=team.head).status_code == 404

    other_head = auth_headers(client, email="other@example.com", name="Other")
    other_room = create_room(client, other_head, "Other room")
    theirs = client.post(f"{API}/rooms/{other_room['id']}/templates", json={"name": "Secret", "stages": [{"title": "S"}]}, headers=other_head).json()
    assert client.get(url(team, theirs), headers=team.head).status_code == 404
    assert client.patch(url(team, theirs), json={"name": "Hacked"}, headers=team.head).status_code == 404
    assert client.delete(url(team, theirs), headers=team.head).status_code == 404


def test_non_member_gets_404(client):
    team = make_team(client)
    stranger = auth_headers(client, email="stranger@example.com", name="Stranger")
    assert client.get(url(team), headers=stranger).status_code == 404


# ---------- update ----------

def test_rename_only_keeps_stages(client):
    team = make_team(client)
    t = create(client, team)
    r = client.patch(url(team, t), json={"name": "Long video"}, headers=team.head)
    assert r.status_code == 200
    assert r.json()["name"] == "Long video" and len(r.json()["stages"]) == 3


def test_stages_are_replaced_as_a_whole(client):
    team = make_team(client)
    t = create(client, team)
    r = client.patch(url(team, t), json={"stages": [{"title": "Brief"}, {"title": "Publish"}]}, headers=team.head)
    assert [s["title"] for s in r.json()["stages"]] == ["Brief", "Publish"]
    assert [s["position"] for s in r.json()["stages"]] == [1, 2]
    assert client.get(url(team, t), headers=team.head).json()["stages"][0]["title"] == "Brief"


def test_update_validation(client):
    team = make_team(client)
    t = create(client, team)
    create(client, team, name="Article", stages=[{"title": "Write"}])
    assert "name" in err(client.patch(url(team, t), json={"name": None}, headers=team.head), 422)["fields"]
    assert "stages" in err(client.patch(url(team, t), json={"stages": None}, headers=team.head), 422)["fields"]
    assert "stages" in err(client.patch(url(team, t), json={"stages": []}, headers=team.head), 422)["fields"]
    assert "name" in err(client.patch(url(team, t), json={"name": "article"}, headers=team.head), 409, "CONFLICT")["fields"]
    r = client.patch(url(team, t), json={"stages": [{"title": "A", "parallel_with_previous": True}]}, headers=team.head)
    assert "stages.0.parallel_with_previous" in err(r, 422)["fields"]


def test_renaming_to_the_same_name_with_different_case_is_fine(client):
    team = make_team(client)
    t = create(client, team)
    assert client.patch(url(team, t), json={"name": "VIDEO SHOOT"}, headers=team.head).json()["name"] == "VIDEO SHOOT"


# ---------- delete ----------

def test_delete_template(client):
    team = make_team(client)
    t = create(client, team)
    assert client.delete(url(team, t), headers=team.head).status_code == 204
    assert client.get(url(team, t), headers=team.head).status_code == 404
    assert client.get(url(team), headers=team.head).json()["total"] == 0


# ---------- permissions ----------

def test_members_cannot_create_edit_delete_or_apply(client):
    team = make_team(client)
    t = create(client, team)
    assert client.post(url(team), json=video_shoot(team, name="Mine"), headers=team.femi).status_code == 403
    assert client.patch(url(team, t), json={"name": "X"}, headers=team.femi).status_code == 403
    assert client.delete(url(team, t), headers=team.femi).status_code == 403
    r = client.post(url(team, t) + "/apply", json={"title": "X", "due_date": FAR_FUTURE}, headers=team.femi)
    assert r.status_code == 403


# ---------- apply ----------

def apply(client, team, t, headers=None, **body):
    body.setdefault("title", "Product promo video")
    body.setdefault("due_date", FAR_FUTURE)
    return client.post(url(team, t) + "/apply", json=body, headers=headers or team.head)


def test_apply_creates_a_task_copying_titles_tags_and_parallel_flags(client):
    team = make_team(client)
    t = create(client, team, stages=[
        {"title": "Script", "tag_id": team.tags["Content Writer"]["id"]},
        {"title": "Graphics"},
        {"title": "Music", "parallel_with_previous": True},
    ])
    r = apply(client, team, t, description="30s cut", start_date="2099-10-01T00:00:00Z")
    assert r.status_code == 201
    task = r.json()
    assert (task["title"], task["description"], task["start_date"], task["due_date"]) == (
        "Product promo video", "30s cut", "2099-10-01T00:00:00Z", FAR_FUTURE,
    )
    assert [s["title"] for s in task["stages"]] == ["Script", "Graphics", "Music"]
    assert [s["step"] for s in task["stages"]] == [1, 2, 2]
    assert [s["status"] for s in task["stages"]] == ["todo", "locked", "locked"]
    assert task["stages"][0]["tag"]["name"] == "Content Writer"
    assert all(s["assignees"] == [] and s["due_date"] is None for s in task["stages"])  # head fills these in after
    assert (task["status"], task["progress"], task["created_by"]["name"]) == ("not_started", 0, "Ada")


def test_applied_task_works_like_any_other(client):
    team = make_team(client)
    t = create(client, team)
    task = apply(client, team, t).json()
    r = put_status(client, team, task, task["stages"][0], "done", team.femi)  # Femi holds the Script tag
    assert r.status_code == 200 and r.json()["progress"] == 33


def test_apply_validation(client):
    team = make_team(client)
    t = create(client, team)
    assert "due_date" in err(client.post(url(team, t) + "/apply", json={"title": "X"}, headers=team.head), 422)["fields"]
    assert "due_date" in err(apply(client, team, t, due_date="2099-10-30T17:00:00"), 422)["fields"]  # no timezone
    assert "title" in err(apply(client, team, t, title="  "), 422)["fields"]
    assert "start_date" in err(apply(client, team, t, start_date="2100-01-01T00:00:00Z"), 422)["fields"]


def test_apply_unknown_or_foreign_template_is_404(client):
    team = make_team(client)
    assert apply(client, team, str(uuid.uuid4())).status_code == 404


def test_editing_a_template_never_changes_tasks_already_made_from_it(client):
    team = make_team(client)
    t = create(client, team)
    task = apply(client, team, t).json()
    client.patch(url(team, t), json={"name": "Renamed", "stages": [{"title": "Totally different"}]}, headers=team.head)
    client.delete(url(team, t), headers=team.head)
    after = get_task(client, team, task)
    assert [s["title"] for s in after["stages"]] == ["Script", "Shoot", "Edit"]


# ---------- tag cleanup ----------

def test_deleting_a_tag_clears_it_from_template_stages_and_apply_still_works(client):
    team = make_team(client)
    t = create(client, team)
    tag = team.tags["Videographer"]
    client.delete(f"{API}/rooms/{team.room['id']}/tags/{tag['id']}", headers=team.head)

    stages = client.get(url(team, t), headers=team.head).json()["stages"]
    assert stages[1]["tag"] is None and stages[0]["tag"]["name"] == "Content Writer"

    task = apply(client, team, t).json()
    assert task["stages"][1]["tag"] is None
