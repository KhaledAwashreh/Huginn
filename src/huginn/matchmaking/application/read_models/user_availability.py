from enum import StrEnum


class UserAvailability(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    MISSING = "missing"
