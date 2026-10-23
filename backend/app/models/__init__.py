# Import every model here so Base.metadata (used by Alembic) sees all tables.
from app.models.calendar import CalendarFeed  # noqa: F401
from app.models.email import EmailChangeToken, OutboxEmail, PasswordResetToken  # noqa: F401
from app.models.message import Message  # noqa: F401
from app.models.notification import MutedRoom, Notification, NotificationSettings  # noqa: F401
from app.models.progress import ProgressUpdate  # noqa: F401
from app.models.push import PushSubscription, ServerKey  # noqa: F401
from app.models.refresh_token import RefreshToken  # noqa: F401
from app.models.room import Membership, Room, RoomInvite, TempHead  # noqa: F401
from app.models.tag import MembershipTag, Tag  # noqa: F401
from app.models.task import Stage, StageAssignee, Task  # noqa: F401
from app.models.template import TaskTemplate, TemplateStage  # noqa: F401
from app.models.user import User  # noqa: F401
