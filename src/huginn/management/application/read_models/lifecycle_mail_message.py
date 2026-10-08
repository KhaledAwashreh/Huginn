"""Secret-bearing message input for lifecycle mail rendering."""

from dataclasses import dataclass, field
from typing import Literal

LifecycleMailPurpose = Literal["verify_email", "reset_password"]


@dataclass(frozen=True, slots=True)
class LifecycleMailMessage:
    recipient: str = field(repr=False)
    purpose: LifecycleMailPurpose
    token: str = field(repr=False)
