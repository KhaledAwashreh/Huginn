from typing import Protocol
from uuid import UUID

from huginn.management.domain.entities.command_receipt import CommandReceipt


class CommandReceiptRepository(Protocol):
    def get_by_key(
        self, business_id: UUID, idempotency_key: str
    ) -> CommandReceipt | None:
        """Look up by Business and request key only; compare scope and fingerprint afterward."""
        ...

    def record(self, receipt: CommandReceipt) -> CommandReceipt:
        """Store immutable committed outcome snapshot and version; reject key conflicts."""
        ...
