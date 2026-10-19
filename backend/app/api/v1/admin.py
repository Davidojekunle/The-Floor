"""Staff only: the health and usage totals behind the /admin page. Everyone else gets a 404."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_staff
from app.core.openapi import err
from app.db.session import get_db
from app.models.user import User
from app.schemas.admin import AdminStats
from app.services import admin_service

router = APIRouter()


@router.get(
    "/stats",
    response_model=AdminStats,
    responses={401: err("Missing, invalid, or expired token."), 404: err("Not staff.")},
)
def get_admin_stats(_: User = Depends(require_staff), db: Session = Depends(get_db)):
    """Is the app healthy, and is it being used? Counts only: no names, titles or messages."""
    return admin_service.stats(db)
