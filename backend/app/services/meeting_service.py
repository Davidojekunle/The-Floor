"""Calls, C2: scheduled meetings (contract v4).

A meeting is a call row with kind "scheduled": it waits as "scheduled" until its first person joins (from 10 minutes
before the start), then behaves like any live call (call_service). A repeating meeting is one row per occurrence
sharing a series_id. Invites are people and tags; tags are resolved to people whenever someone is told, so a person
who gains the tag later is included. Meeting emails go out at once (not grouped) with a calendar file attached.
"""
import uuid
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import CallEnded, Forbidden, NotFound, TaskNotApproved, ValidationFailed
from app.models.call import Call, CallInvite, CallKind, CallStatus
from app.models.enums import ApprovalStatus, MembershipStatus
from app.models.room import Membership, Room
from app.models.tag import MembershipTag, Tag
from app.models.task import Task
from app.models.user import User
from app.permissions.rules import RoomContext, can, require
from app.realtime import events as live
from app.services import chat_service, email_service
from app.utils.time import as_utc, utcnow

JOIN_EARLY = timedelta(minutes=10)
REMIND_BEFORE = timedelta(minutes=10)
REPEAT_DAYS = {"week": 7, "2weeks": 14}
MAX_OCCURRENCES = 26  # half a year of weekly meetings
INVALID = "Some fields are invalid."


def _zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def when(dt: datetime, tz_name: str | None) -> str:
    """"Mon 2 Nov, 10:00" in someone's timezone."""
    local = as_utc(dt).astimezone(_zone(tz_name))
    return local.strftime("%a %d %b, %H:%M").replace(" 0", " ")


# ================================================================== who's invited

def _active_members(db: Session, room_id) -> set:
    return set(db.scalars(select(Membership.user_id).where(Membership.room_id == room_id,
                                                           Membership.status == MembershipStatus.ACTIVE)))


def _tag_holders(db: Session, room_id, tag_ids) -> set:
    if not tag_ids:
        return set()
    return set(db.scalars(
        select(Membership.user_id).join(MembershipTag, MembershipTag.membership_id == Membership.id)
        .where(MembershipTag.tag_id.in_(list(tag_ids)), Membership.room_id == room_id,
               Membership.status == MembershipStatus.ACTIVE)
    ))


def resolve(db: Session, room_id, *, everyone: bool, user_ids, tag_ids) -> set:
    """The people an invite means right now: active members only."""
    members = _active_members(db, room_id)
    if everyone:
        return members
    return (set(user_ids) | _tag_holders(db, room_id, tag_ids)) & members


def invitees(db: Session, call: Call) -> set:
    rows = db.scalars(select(CallInvite).where(CallInvite.call_id == call.id)).all()
    return resolve(db, call.room_id, everyone=call.invite_everyone,
                   user_ids=[r.user_id for r in rows if r.user_id], tag_ids=[r.tag_id for r in rows if r.tag_id])


def invite_out(db: Session, call: Call) -> dict:
    rows = db.scalars(select(CallInvite).where(CallInvite.call_id == call.id)).all()
    uids = [r.user_id for r in rows if r.user_id]
    tids = [r.tag_id for r in rows if r.tag_id]
    users = db.execute(select(User.id, User.name).where(User.id.in_(uids))).all() if uids else []
    tags = db.execute(select(Tag.id, Tag.name).where(Tag.id.in_(tids))).all() if tids else []
    return {"everyone": call.invite_everyone, "users": [{"id": i, "name": n} for i, n in users],
            "tags": [{"id": i, "name": n} for i, n in tags]}


def _set_invites(db: Session, call: Call, invite) -> None:
    call.invite_everyone = invite.everyone
    for row in db.scalars(select(CallInvite).where(CallInvite.call_id == call.id)).all():
        db.delete(row)
    if not invite.everyone:
        for uid in dict.fromkeys(invite.user_ids):
            db.add(CallInvite(call_id=call.id, user_id=uid))
        for tid in dict.fromkeys(invite.tag_ids):
            db.add(CallInvite(call_id=call.id, tag_id=tid))


# ================================================================== checks

def can_edit(ctx: RoomContext, call: Call) -> bool:
    return call.kind == CallKind.SCHEDULED and call.status == CallStatus.SCHEDULED and (
        call.created_by == ctx.membership.user_id or can(ctx, "call.manage_any"))


def _check_invite(db: Session, ctx: RoomContext, invite) -> None:
    if invite.everyone:
        return
    if not invite.user_ids and not invite.tag_ids:
        raise ValidationFailed(INVALID, fields={"invite": "Invite everyone, some people, or a tag."})
    members = _active_members(db, ctx.room.id)
    if any(u not in members for u in invite.user_ids):
        raise ValidationFailed(INVALID, fields={"invite.user_ids": "Everyone invited must be in this room."})
    if invite.tag_ids:
        known = set(db.scalars(select(Tag.id).where(Tag.room_id == ctx.room.id, Tag.id.in_(invite.tag_ids))))
        if any(t not in known for t in invite.tag_ids):
            raise ValidationFailed(INVALID, fields={"invite.tag_ids": "Unknown tag in this room."})


def _check_time(starts_at: datetime) -> datetime:
    starts_at = as_utc(starts_at)
    if starts_at <= utcnow():
        raise ValidationFailed(INVALID, fields={"starts_at": "Pick a time in the future."})
    return starts_at


def _task(db: Session, ctx: RoomContext, task_id) -> Task | None:
    if task_id is None:
        return None
    task = db.scalar(select(Task).where(Task.id == task_id, Task.room_id == ctx.room.id))
    if task is None:
        raise NotFound("Task not found.")
    if task.approval_status != ApprovalStatus.APPROVED:
        raise TaskNotApproved("A meeting about a task can be scheduled once the task is approved.")
    return task


def _meeting(db: Session, ctx: RoomContext, call_id) -> Call:
    call = db.scalar(select(Call).where(Call.id == call_id, Call.room_id == ctx.room.id,
                                        Call.kind == CallKind.SCHEDULED))
    if call is None:
        raise NotFound("Meeting not found.")
    return call


def _occurrences(starts_at: datetime, repeat, tz_name: str) -> list[datetime]:
    if repeat is None:
        return [starts_at]
    step = timedelta(days=REPEAT_DAYS[repeat.every])
    last = datetime.combine(repeat.until, time(23, 59), tzinfo=_zone(tz_name))  # the end of that day, for the organiser
    if last < starts_at:
        raise ValidationFailed(INVALID, fields={"repeat.until": "The last date must be on or after the first meeting."})
    out = []
    # step in the organiser's local time, so "every Monday at 10:00" stays at 10:00 across clock changes
    local = starts_at.astimezone(_zone(tz_name))
    while len(out) < MAX_OCCURRENCES:
        at = (local + step * len(out)).replace(tzinfo=None)
        occurrence = at.replace(tzinfo=_zone(tz_name))
        if occurrence > last:
            break
        out.append(as_utc(occurrence))
    return out


# ================================================================== clashes

def clashes(db: Session, ctx: RoomContext, *, starts_at, duration_minutes: int, invite, exclude_id=None) -> list[dict]:
    """Who among the invitees already has a meeting then (in any of their rooms). A note, never a block."""
    people = resolve(db, ctx.room.id, everyone=invite.everyone, user_ids=invite.user_ids, tag_ids=invite.tag_ids)
    if not people:
        return []
    start = as_utc(starts_at)
    end = start + timedelta(minutes=duration_minutes)
    rooms = set(db.scalars(select(Membership.room_id).where(Membership.user_id.in_(people),
                                                            Membership.status == MembershipStatus.ACTIVE)))
    others = db.scalars(select(Call).where(
        Call.room_id.in_(rooms), Call.kind == CallKind.SCHEDULED,
        Call.status.in_([CallStatus.SCHEDULED, CallStatus.LIVE]),
        Call.starts_at < end, Call.ends_at_planned > start,
        *([Call.id != exclude_id] if exclude_id else []),
    )).all()
    names = dict(db.execute(select(User.id, User.name).where(User.id.in_(people))).all())
    found = []
    for other in sorted(others, key=lambda c: as_utc(c.starts_at)):
        room = db.get(Room, other.room_id)
        for uid in sorted(invitees(db, other) & people, key=lambda u: names.get(u, "")):
            found.append({"user": {"id": uid, "name": names[uid]}, "title": other.title,
                          "starts_at": as_utc(other.starts_at), "room_name": room.name if room else ""})
    return found


# ================================================================== calendar files

def ics(calls: list[Call], *, cancel: bool = False) -> str:
    from app.services.calendar_service import _escape, _fold

    base = get_settings().frontend_url.rstrip("/")
    stamp = utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//The Floor//Meetings//EN", "CALSCALE:GREGORIAN",
             f"METHOD:{'CANCEL' if cancel else 'PUBLISH'}"]
    for c in calls:
        url = c.external_url or f"{base}/rooms/{c.room_id}/calls/{c.id}"
        lines += [
            "BEGIN:VEVENT", f"UID:meeting-{c.id}@the-floor", f"SEQUENCE:{c.ics_sequence}", f"DTSTAMP:{stamp}",
            f"DTSTART:{as_utc(c.starts_at).strftime('%Y%m%dT%H%M%SZ')}",
            f"DTEND:{as_utc(c.ends_at_planned).strftime('%Y%m%dT%H%M%SZ')}",
            f"SUMMARY:{_escape(c.title)}",
            f"DESCRIPTION:{_escape(((c.description or '') + chr(10) + chr(10) + 'Join: ' + url).strip())}",
            f"URL:{url}", f"LOCATION:{_escape(url)}",
            f"STATUS:{'CANCELLED' if cancel else 'CONFIRMED'}", "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def _email(db: Session, room: Room, user_id, subject: str, title: str, paragraphs: list[str],
           button: tuple[str, str] | None, calendar: str | None, cancel: bool = False) -> None:
    """Straight away (a meeting email can't wait for grouping), if this person gets calls emails from this room."""
    from app.services import notification_service as notes
    from app.services.account_service import gets_notification_emails
    from app.services.notification_email import LABEL, unsubscribe_url

    user = db.get(User, user_id)
    s = notes.settings_for(db, user_id)
    if user is None or not (s.email_enabled and s.calls) or not gets_notification_emails(user) \
            or notes.is_muted(db, user_id, room.id):
        return
    url = unsubscribe_url(user.id, "calls")
    text, html_body = email_service.render(title, [f"Hi {user.name},", *paragraphs], button=button,
                                           footer=f"You get these emails for {LABEL['calls']}.",
                                           footer_link=("Turn them off", url))
    attachments = [{"filename": "invite.ics" if not cancel else "cancel.ics",
                    "content_type": f"text/calendar; method={'CANCEL' if cancel else 'PUBLISH'}",
                    "content": calendar}] if calendar else None
    email_service.queue(db, to=user.email, subject=subject, text=text, html_body=html_body, category="calls",
                        user_id=user.id, attachments=attachments,
                        headers={"List-Unsubscribe": f"<{url}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"})


def _tell(db: Session, ctx: RoomContext | None, room: Room, call: Call, kind: str, people: set, actor: User | None,
          title: str, email_subject: str, paragraphs, calendar: str | None, cancel: bool = False) -> None:
    from app.services import notification_service as notes

    base = get_settings().frontend_url.rstrip("/")
    task = db.get(Task, call.task_id) if call.task_id else None
    for uid in people:
        if actor is not None and uid == actor.id:
            continue  # never for your own actions
        notes.notify(db, uid, kind, title, room=room, task=task, actor=actor, data={"call_id": str(call.id)})
        target = f"{base}/rooms/{room.id}/calls/{call.id}" if not cancel else f"{base}/rooms/{room.id}/calls"
        _email(db, room, uid, email_subject, title, paragraphs(uid), ("Open in The Floor", target), calendar, cancel)


# ================================================================== scheduling

def schedule(db: Session, ctx: RoomContext, body) -> Call:
    require(ctx, "meeting.schedule", "Only the head or a temp head can schedule meetings.")
    task = _task(db, ctx, body.task_id)
    _check_invite(db, ctx, body.invite)
    starts_at = _check_time(body.starts_at)
    organiser = db.get(User, ctx.membership.user_id)
    duration = timedelta(minutes=body.duration_minutes)
    series = uuid.uuid4() if body.repeat else None
    calls = []
    for at in _occurrences(starts_at, body.repeat, organiser.timezone):
        call = Call(room_id=ctx.room.id, task_id=task.id if task else None, kind=CallKind.SCHEDULED,
                    status=CallStatus.SCHEDULED, title=body.title.strip(), description=(body.description or "").strip() or None,
                    starts_at=at, ends_at_planned=at + duration, created_by=organiser.id,
                    external_url=body.external_url, series_id=series)
        db.add(call)
        db.flush()
        _set_invites(db, call, body.invite)
        calls.append(call)
    db.flush()
    first = calls[0]
    repeat_note = (f"every {'week' if body.repeat.every == 'week' else 'two weeks'} until "
                   f"{body.repeat.until.strftime('%d %b').lstrip('0')}") if body.repeat else None
    chat_service.post_system(db, room_id=ctx.room.id, event="meeting_scheduled", actor_id=organiser.id, task=task,
                             detail={"call_id": str(first.id), "title": first.title,
                                     "starts_at": as_utc(first.starts_at).isoformat(), "repeat": repeat_note})
    people = invitees(db, first)
    _tell(db, ctx, ctx.room, first, "meeting_scheduled", people, organiser,
          f"{organiser.name} invited you to {first.title}",
          f"Invitation: {first.title} · {when(first.starts_at, organiser.timezone)}",
          lambda uid: _when_lines(db, uid, first, repeat_note), ics(calls))
    for c in calls:
        live.call_changed(db, c)
    db.commit()
    return first


def _when_lines(db: Session, uid, call: Call, repeat_note: str | None = None) -> list[str]:
    user = db.get(User, uid)
    tz = user.timezone if user else None
    mins = int((as_utc(call.ends_at_planned) - as_utc(call.starts_at)).total_seconds() // 60)
    lines = [f"{call.title}: {when(call.starts_at, tz)} ({mins} min){', ' + repeat_note if repeat_note else ''}."]
    if call.description:
        lines.append(call.description)
    lines.append(f"Join by link: {call.external_url}" if call.external_url
                 else "Join from The Floor, from 10 minutes before the start. The calendar file adds it to your calendar.")
    return lines


def update(db: Session, ctx: RoomContext, call_id, changes: dict) -> Call:
    call = _meeting(db, ctx, call_id)
    if call.status != CallStatus.SCHEDULED:
        raise CallEnded("This meeting has already started or finished.")
    if not can_edit(ctx, call):
        raise Forbidden("Only whoever scheduled it, the head or a temp head can change this meeting.")
    actor = db.get(User, ctx.membership.user_id)
    before_people = invitees(db, call)
    duration = changes.get("duration_minutes") or int(
        (as_utc(call.ends_at_planned) - as_utc(call.starts_at)).total_seconds() // 60)
    moved = False
    if "starts_at" in changes and as_utc(changes["starts_at"]) != as_utc(call.starts_at):
        call.starts_at = _check_time(changes["starts_at"])
        call.reminded_at = None
        moved = True
    if "duration_minutes" in changes:
        moved = moved or changes["duration_minutes"] != int((as_utc(call.ends_at_planned) - as_utc(call.starts_at)).total_seconds() // 60)
    call.ends_at_planned = as_utc(call.starts_at) + timedelta(minutes=duration)
    if "title" in changes:
        call.title = changes["title"].strip()
    if "description" in changes:
        call.description = (changes["description"] or "").strip() or None
    if "external_url" in changes and changes["external_url"] != call.external_url:
        call.external_url = changes["external_url"]
        moved = True
    if "task_id" in changes:
        task = _task(db, ctx, changes["task_id"])
        call.task_id = task.id if task else None
    if "invite" in changes:
        _check_invite(db, ctx, changes["invite"])
        _set_invites(db, call, changes["invite"])
    call.ics_sequence += 1
    db.flush()
    after_people = invitees(db, call)
    if moved or "title" in changes:
        _tell(db, ctx, ctx.room, call, "meeting_updated", after_people & before_people, actor,
              f"{actor.name} changed {call.title}", f"Updated: {call.title} · {when(call.starts_at, actor.timezone)}",
              lambda uid: _when_lines(db, uid, call), ics([call]))
    new_people = after_people - before_people
    if new_people:
        _tell(db, ctx, ctx.room, call, "meeting_scheduled", new_people, actor,
              f"{actor.name} invited you to {call.title}",
              f"Invitation: {call.title} · {when(call.starts_at, actor.timezone)}",
              lambda uid: _when_lines(db, uid, call), ics([call]))
    removed = before_people - after_people
    if removed:
        _tell(db, ctx, ctx.room, call, "meeting_cancelled", removed, actor,
              f"You're no longer invited to {call.title}", f"Cancelled for you: {call.title}",
              lambda uid: [f"{call.title} on {when(call.starts_at, actor.timezone)} no longer includes you."],
              ics([call], cancel=True), cancel=True)
    live.call_changed(db, call)
    db.commit()
    return call


def cancel(db: Session, ctx: RoomContext, call_id, *, following: bool) -> None:
    call = _meeting(db, ctx, call_id)
    if call.status != CallStatus.SCHEDULED:
        raise CallEnded("This meeting has already started or finished.")
    if not can_edit(ctx, call):
        raise Forbidden("Only whoever scheduled it, the head or a temp head can cancel this meeting.")
    actor = db.get(User, ctx.membership.user_id)
    targets = [call]
    if following and call.series_id:
        targets += db.scalars(select(Call).where(Call.series_id == call.series_id, Call.id != call.id,
                                                 Call.status == CallStatus.SCHEDULED,
                                                 Call.starts_at > call.starts_at)).all()
    people = set()
    for c in targets:
        people |= invitees(db, c)
        c.status, c.ics_sequence = CallStatus.CANCELLED, c.ics_sequence + 1
    db.flush()
    which = "and the ones after it" if len(targets) > 1 else ""
    task = db.get(Task, call.task_id) if call.task_id else None
    chat_service.post_system(db, room_id=ctx.room.id, event="meeting_cancelled", actor_id=actor.id, task=task,
                             detail={"call_id": str(call.id), "title": call.title,
                                     "starts_at": as_utc(call.starts_at).isoformat(), "count": len(targets)})
    _tell(db, ctx, ctx.room, call, "meeting_cancelled", people, actor, f"{actor.name} cancelled {call.title}",
          f"Cancelled: {call.title} · {when(call.starts_at, actor.timezone)}",
          lambda uid: [f"{call.title} on {when(call.starts_at, db.get(User, uid).timezone)} {which} won't happen.".replace("  ", " ")],
          ics(targets, cancel=True), cancel=True)
    for c in targets:
        live.call_changed(db, c)
    db.commit()


# ================================================================== joining a meeting

def open_for_joining(db: Session, ctx: RoomContext, call: Call):
    """Called by call_service.join_call for a scheduled meeting. Returns "link" for a pasted link, else readies the
    call (live from its first join). Too early raises CallNotOpen."""
    from app.core.errors import CallNotOpen
    from app.services import video

    now = utcnow()
    if now < as_utc(call.starts_at) - JOIN_EARLY:
        user = db.get(User, ctx.membership.user_id)
        opens = as_utc(call.starts_at) - JOIN_EARLY
        raise CallNotOpen(f"You can join from {opens.astimezone(_zone(user.timezone)).strftime('%H:%M')}, "
                          "10 minutes before it starts.")
    if call.external_url:
        return "link"
    s = get_settings()
    call.provider_room = call.provider_room or f"floor-{uuid.uuid4().hex[:20]}"
    call.hard_stop_at = now + timedelta(minutes=s.call_max_minutes)
    video.provider().create_room(call.provider_room, call.hard_stop_at, s.call_max_participants)
    call.status, call.started_at, call.empty_since = CallStatus.LIVE, now, now
    live.call_changed(db, call)
    db.commit()
    return "live"


# ================================================================== the minute check: reminders and missed meetings

def due_work(db: Session) -> None:
    """Reminders 10 minutes before; meetings nobody joined by their planned end are marked missed. Caller commits."""
    now = utcnow()
    for call in db.scalars(select(Call).where(Call.kind == CallKind.SCHEDULED, Call.status == CallStatus.SCHEDULED,
                                              Call.reminded_at.is_(None), Call.starts_at <= now + REMIND_BEFORE,
                                              Call.starts_at > now - REMIND_BEFORE)).all():
        call.reminded_at = now
        room = db.get(Room, call.room_id)
        if room is None:
            continue
        _tell(db, None, room, call, "meeting_reminder", invitees(db, call), None,
              f"{call.title} starts in 10 minutes",
              f"Starting soon: {call.title}", lambda uid: _when_lines(db, uid, call), None)
    for call in db.scalars(select(Call).where(Call.kind == CallKind.SCHEDULED, Call.status == CallStatus.SCHEDULED,
                                              Call.ends_at_planned <= now)).all():
        call.status, call.ended_at = CallStatus.ENDED, call.ends_at_planned
        call.missed = call.external_url is None  # a pasted-link meeting may well have happened elsewhere
        live.call_changed(db, call)


# ================================================================== reading

def mine(db: Session, user: User, start: datetime, end: datetime) -> list[Call]:
    """My calendar: meetings I'm invited to in my rooms, in the window (and live calls in my rooms)."""
    rooms = set(db.scalars(select(Membership.room_id).where(Membership.user_id == user.id,
                                                            Membership.status == MembershipStatus.ACTIVE)))
    if not rooms:
        return []
    rows = db.scalars(select(Call).where(Call.room_id.in_(rooms), or_(
        and_(Call.kind == CallKind.SCHEDULED, Call.starts_at < end, Call.ends_at_planned > start),
        Call.status == CallStatus.LIVE,
    )).order_by(Call.starts_at)).all()
    return [c for c in rows if c.kind != CallKind.SCHEDULED or user.id in invitees(db, c)]


def for_feed(db: Session, user: User, room_id=None) -> list[Call]:
    """Calendar subscriptions: upcoming and recent meetings (personal feed: those I'm invited to)."""
    start, end = utcnow() - timedelta(days=30), utcnow() + timedelta(days=200)
    if room_id is None:
        return [c for c in mine(db, user, start, end) if c.kind == CallKind.SCHEDULED and c.status != CallStatus.CANCELLED]
    return list(db.scalars(select(Call).where(Call.room_id == room_id, Call.kind == CallKind.SCHEDULED,
                                              Call.status != CallStatus.CANCELLED, Call.starts_at < end,
                                              Call.ends_at_planned > start)))
