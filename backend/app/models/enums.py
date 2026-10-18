"""Plain string constants (not Enum classes) so they bind cleanly to String columns."""


class Role:
    HEAD = "head"
    TEMP_HEAD = "temp_head"  # derived at request time, never stored on Membership
    MEMBER = "member"


class MembershipStatus:
    PENDING = "pending"
    ACTIVE = "active"
    REJECTED = "rejected"
    REMOVED = "removed"


class StageStatus:
    LOCKED = "locked"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"


class TaskStatus:
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class ApprovalStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
