"""Demo data for local development. Safe to run more than once.

    cd backend
    python -m scripts.seed

Creates a demo room with a head, two approved members (each with a tag), one
pending join request, a "Video shoot" template, and a three-stage task made from it
with the first stage done and the next one assigned to Tola, so every screen
(including My Tasks and the "for you" badges) has something to show. Everything goes
through the real services, so the data follows the same rules as the API.

To wipe the database and start over:  alembic downgrade base && alembic upgrade head
"""
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.enums import MembershipStatus
from app.models.room import Membership, Room
from app.models.task import Task
from app.models.template import TaskTemplate
from app.models.user import User
from app.schemas.common import PageParams
from app.schemas.message import MessageCreate
from app.schemas.task import StageIn, StageUpdate, StatusUpdate, TaskCreate
from app.schemas.template import TemplateApply, TemplateCreate, TemplateStageIn
from app.services import (
    auth_service,
    chat_service,
    member_service,
    room_service,
    stage_service,
    tag_service,
    task_service,
    template_service,
)
from app.utils.time import utcnow

PASSWORD = "password123"
ROOM_NAME = "Studio Alpha"

HEAD = ("Ada", "head@example.com")
MEMBERS = [  # (name, email, tag they get when they first join)
    ("Femi", "femi@example.com", "Content Writer"),
    ("Tola", "tola@example.com", "Video Editor"),
]
PENDING = ("Kemi", "kemi@example.com")
TAGS = ["Content Writer", "Videographer", "Video Editor", "Graphic Designer"]
TEMPLATE_NAME = "Video shoot"
TEMPLATE_STAGES = [("Script", "Content Writer"), ("Shoot", "Videographer"), ("Edit", "Video Editor")]
TASK_TITLE = "Product promo video"
PROPOSAL_TITLE = "Behind-the-scenes reel"


def _user(db: Session, name: str, email: str) -> User:
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        return existing
    return auth_service.register_user(db, name=name, email=email, password=PASSWORD, timezone="Africa/Lagos")


def _membership(db: Session, room_id, user_id) -> Membership | None:
    return db.scalar(select(Membership).where(Membership.room_id == room_id, Membership.user_id == user_id))


def run(db: Session) -> dict:
    head = _user(db, *HEAD)

    room = db.scalar(select(Room).where(Room.name == ROOM_NAME, Room.created_by == head.id))
    if room is None:
        ctx = room_service.create_room(db, head, ROOM_NAME)
    else:
        ctx = room_service.get_room_context(db, room.id, head)

    # tags (only the missing ones)
    existing_tags, _ = tag_service.list_tags(db, ctx, PageParams(page=1, limit=100))
    tag_ids = {t.name: t.id for t in existing_tags}
    for name in TAGS:
        if name not in tag_ids:
            tag_ids[name] = tag_service.create_tag(db, ctx, name).id

    # approved members; their tag is set only when they first join, so manual edits survive a re-run
    users = {}
    for name, email, tag_name in MEMBERS:
        user = users[name] = _user(db, name, email)
        m = _membership(db, ctx.room.id, user.id)
        if m is not None and m.status == MembershipStatus.ACTIVE:
            continue
        joined = room_service.request_join(db, user, ctx.room.invite_code)
        room_service.decide_join_request(db, ctx, joined.membership_id, approve=True)
        member_service.set_member_tags(db, ctx, joined.membership_id, [tag_ids[tag_name]])

    # one pending request, so the head's badge and join-requests screen have data
    pending_user = _user(db, *PENDING)
    if _membership(db, ctx.room.id, pending_user.id) is None:
        room_service.request_join(db, pending_user, ctx.room.invite_code)

    # a template and a task made from it, with Script already done by Femi (progress 33%)
    if db.scalar(select(TaskTemplate.id).where(TaskTemplate.room_id == ctx.room.id, TaskTemplate.name == TEMPLATE_NAME)) is None:
        template_service.create_template(
            db, ctx,
            TemplateCreate(name=TEMPLATE_NAME, stages=[TemplateStageIn(title=t, tag_id=tag_ids[tag]) for t, tag in TEMPLATE_STAGES]),
        )
    if db.scalar(select(Task.id).where(Task.room_id == ctx.room.id, Task.title == TASK_TITLE)) is None:
        template = db.scalar(select(TaskTemplate).where(TaskTemplate.room_id == ctx.room.id, TaskTemplate.name == TEMPLATE_NAME))
        due = (utcnow() + timedelta(days=14)).replace(hour=17, minute=0, second=0, microsecond=0)
        task = template_service.apply_template(
            db, ctx, template.id, TemplateApply(title=TASK_TITLE, description="30s cut for Instagram", due_date=due)
        )
        femi_ctx = room_service.get_room_context(db, ctx.room.id, users["Femi"])
        stage_service.set_status(db, femi_ctx, task.id, task.stages[0].id, StatusUpdate(status="done"))
        # nobody holds the Videographer tag, so assign Shoot to Tola directly: she now has work waiting
        # (Shoot, assigned to her) and work coming (Edit, via her Video Editor tag)
        stage_service.update_stage(db, ctx, task.id, task.stages[1].id, StageUpdate(assignee_ids=[users["Tola"].id]))
        tola_ctx = room_service.get_room_context(db, ctx.room.id, users["Tola"])
        chat_service.send_message(
            db, tola_ctx, MessageCreate(body="Shooting starts tomorrow at 9", task_id=task.id, stage_id=task.stages[1].id)
        )

    # a member's proposal waiting for the head (approvals screen, "Requests" badge)
    if db.scalar(select(Task.id).where(Task.room_id == ctx.room.id, Task.title == PROPOSAL_TITLE)) is None:
        femi_ctx = room_service.get_room_context(db, ctx.room.id, users["Femi"])
        due = (utcnow() + timedelta(days=21)).replace(hour=17, minute=0, second=0, microsecond=0)
        task_service.create_task(
            db, femi_ctx,
            TaskCreate(
                title=PROPOSAL_TITLE,
                description="Short reel from the promo shoot for socials",
                due_date=due,
                stages=[StageIn(title="Pick clips", tag_id=tag_ids["Video Editor"]), StageIn(title="Captions", tag_id=tag_ids["Content Writer"])],
            ),
        )

    return {
        "room_id": str(ctx.room.id),
        "room_name": ctx.room.name,
        "invite_code": ctx.room.invite_code,
        "template": TEMPLATE_NAME,
        "task": TASK_TITLE,
        "proposal": PROPOSAL_TITLE,
        "logins": [
            {"email": HEAD[1], "name": HEAD[0], "state": "head"},
            *[{"email": e, "name": n, "state": f"member ({t})"} for n, e, t in MEMBERS],
            {"email": PENDING[1], "name": PENDING[0], "state": "pending join request"},
        ],
    }


def main() -> None:
    with SessionLocal() as db:
        result = run(db)
    print(f"Seeded '{result['room_name']}'  (id: {result['room_id']})")
    print(f"Invite code: {result['invite_code']}   (join link: /join/{result['invite_code']})")
    print(f"Template:    {result['template']}   Task: {result['task']} (Script done, 33%; Shoot assigned to Tola)")
    print(f"Proposal:    {result['proposal']} (pending, proposed by Femi)")
    print(f"\nLogins (password for all: {PASSWORD})")
    for login in result["logins"]:
        print(f"  {login['email']:<20} {login['name']:<6} {login['state']}")


if __name__ == "__main__":
    main()
