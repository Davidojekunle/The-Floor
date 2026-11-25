"""Staff only: the health and usage totals behind the /admin page. Everyone else gets a 404."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_staff
from app.core.openapi import err
from app.db.session import get_db
from app.models.user import User
import uuid

from app.schemas.admin import AdminAdd, AdminEventOut, AdminPerson, AdminStats, SiteInfo, SiteSettings, SiteSettingsUpdate
from app.services import admin_people, admin_service, site_service

router = APIRouter()


@router.get(
    "/stats",
    response_model=AdminStats,
    responses={401: err("Missing, invalid, or expired token."), 404: err("Not staff.")},
)
def get_admin_stats(_: User = Depends(require_staff), db: Session = Depends(get_db)):
    """Is the app healthy, and is it being used? Counts only: no names, titles or messages."""
    return admin_service.stats(db)


STAFF_ONLY = {401: err("Missing, invalid, or expired token."), 404: err("Not staff.")}


def _settings(db: Session) -> SiteSettings:
    from app.services import task_assistant

    return SiteSettings(**{**site_service.get(db), "calls_ready": site_service.calls_ready(),
                           "task_assistant_ready": task_assistant.ready()})


@router.get("/settings", response_model=SiteSettings, responses=STAFF_ONLY)
def get_site_settings(_: User = Depends(require_staff), db: Session = Depends(get_db)):
    """The site-wide switches."""
    return _settings(db)


@router.patch("/settings", response_model=SiteSettings,
              responses={**STAFF_ONLY, 409: err("CONFLICT: calls can't be switched on until LiveKit is set up.")})
def update_site_settings(body: SiteSettingsUpdate, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    """Change switches; each takes effect at once, for everyone."""
    changes = body.model_dump(exclude_unset=True)
    if changes.get("calls", "off") != "off" and not site_service.calls_ready():
        from app.core.errors import Conflict

        raise Conflict("Calls can't be switched on until LiveKit's keys are added to the server's settings.")
    site_service.update(db, user, changes)
    return _settings(db)


@router.get("/admins", response_model=list[AdminPerson], responses=STAFF_ONLY)
def list_admins(_: User = Depends(require_staff), db: Session = Depends(get_db)):
    """Everyone who can open the admin page."""
    return admin_people.list_admins(db)


@router.post("/admins", response_model=list[AdminPerson], responses={**STAFF_ONLY, 404: err("Not the owner, or no such account.")})
def add_admin(body: AdminAdd, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    """Owner only: make someone an admin by their account email."""
    return admin_people.add_admin(db, user, body.email)


@router.delete("/admins/{user_id}", response_model=list[AdminPerson],
               responses={**STAFF_ONLY, 409: err("CONFLICT: the owner can't be removed.")})
def remove_admin(user_id: uuid.UUID, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    """Owner only: stop someone being an admin."""
    return admin_people.remove_admin(db, user, user_id)


@router.get("/log", response_model=list[AdminEventOut], responses=STAFF_ONLY)
def admin_log(_: User = Depends(require_staff), db: Session = Depends(get_db)):
    """The last 50 changes: switches turned on or off, admins added or removed. Newest first."""
    return admin_people.events(db)


public = APIRouter()


@public.get("/site", response_model=SiteInfo)
def get_site(db: Session = Depends(get_db)):
    """For every visitor: whether sign-ups are open, and staff's announcement."""
    return site_service.public(db)
