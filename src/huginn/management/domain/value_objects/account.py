"""Account aggregate values."""

from dataclasses import dataclass
from typing import Literal

AccountStatus = Literal["active", "disabled"]


@dataclass(frozen=True)
class NewAccount:
    username: str
    password_hash: str
    status: AccountStatus = "active"
