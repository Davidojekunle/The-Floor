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
