# Import every model here so Base.metadata (used by Alembic) sees all tables.
from app.models.message import Message  # noqa: F401
from app.models.room import Membership, Room, TempHead  # noqa: F401
from app.models.tag import MembershipTag, Tag  # noqa: F401
from app.models.task import Stage, StageAssignee, Task  # noqa: F401
from app.models.template import TaskTemplate, TemplateStage  # noqa: F401
from app.models.user import User  # noqa: F401
