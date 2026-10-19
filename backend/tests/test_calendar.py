"""Calendar subscription feeds (.ics)."""
import pytest

from app.services.calendar_service import _escape, _fold
from tests.conftest import create_task, make_team, membership_id_for, put_status

API = "/api/v1"


@pytest.fixture
def team(client):
    return make_team(client)


def token_of(links):
    return links["url"].rsplit("/", 1)[1].removesuffix(".ics")


def ics(client, links):
    return client.get(f"{API}/calendar/{token_of(links)}.ics")


def test_my_feed_links(client, team):
    links = client.get(f"{API}/me/calendar-feed", headers=team.femi).json()
    assert links["url"].startswith("http") and links["url"].endswith(".ics")
    assert links["webcal_url"].startswith("webcal://")
    assert links["google_url"].startswith("https://calendar.google.com/calendar/r?cid=webcal%3A%2F%2F")
    assert client.get(f"{API}/me/calendar-feed", headers=team.femi).json() == links  # stable


def test_feed_needs_sign_in_to_get_the_link(client):
    assert client.get(f"{API}/me/calendar-feed").status_code == 401


def test_my_feed_has_my_unfinished_stages_only(client, team):
    task = create_task(client, team, due_date="2099-10-30T17:00:00Z")
    r = ics(client, client.get(f"{API}/me/calendar-feed", headers=team.femi).json())
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/calendar")
    body = r.text
    assert body.startswith("BEGIN:VCALENDAR\r\n") and body.endswith("END:VCALENDAR\r\n")
    assert "X-WR-CALNAME:The Floor · My work" in body
    assert "SUMMARY:Script · Product promo video" in body
    assert "DTSTART;VALUE=DATE:20991030" in body  # Africa/Lagos: still the 30th
    assert "Shoot" not in body and "Edit" not in body  # Tola's and nobody's
    assert f"/rooms/{team.room['id']}/tasks/{task['id']}" in body.replace("\r\n ", "")

    put_status(client, team, task, task["stages"][0], "done", team.femi)
    after = ics(client, client.get(f"{API}/me/calendar-feed", headers=team.femi).json()).text
    assert "Script" not in after  # finished work drops off


def test_reset_kills_the_old_link(client, team):
    old = client.get(f"{API}/me/calendar-feed", headers=team.femi).json()
    new = client.post(f"{API}/me/calendar-feed/reset", headers=team.femi).json()
    assert new["url"] != old["url"]
    assert ics(client, old).status_code == 404
    assert ics(client, new).status_code == 200


def test_room_feed(client, team):
    create_task(client, team)
    links = client.get(f"{API}/rooms/{team.room['id']}/calendar-feed", headers=team.tola).json()
    body = ics(client, links).text
    assert "X-WR-CALNAME:The Floor · Studio Alpha" in body
    assert "SUMMARY:Product promo video" in body
    assert "0 of 3 stages done · Now: Script" in body


def test_room_feed_dies_when_you_leave(client, team):
    links = client.get(f"{API}/rooms/{team.room['id']}/calendar-feed", headers=team.tola).json()
    mid = membership_id_for(client, team.room["id"], team.head, team.ids["tola"])
    assert client.delete(f"{API}/rooms/{team.room['id']}/members/{mid}", headers=team.head).status_code == 204
    assert ics(client, links).status_code == 404


def test_unknown_feed(client):
    assert client.get(f"{API}/calendar/not-a-real-token.ics").status_code == 404


def test_text_is_escaped_and_long_lines_folded():
    assert _escape("a, b; c\\d\ne") == "a\\, b\\; c\\\\d\\ne"
    line = "SUMMARY:" + "é" * 60
    folded = _fold(line)
    assert all(len(part.encode()) <= 75 for part in folded.split("\r\n"))
    assert folded.replace("\r\n ", "") == line
