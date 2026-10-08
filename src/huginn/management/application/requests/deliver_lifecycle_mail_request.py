"""One durable lifecycle mail delivery command."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DeliverLifecycleMailRequest:
    pass
