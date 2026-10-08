"""Purpose-bound proof persistence contract; lifecycle design section 4."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from huginn.management.domain.entities.account_lifecycle_proof import (
    AccountLifecycleProof,
)
from huginn.management.domain.value_objects.proof_purpose import ProofPurpose


class AccountLifecycleProofRepository(Protocol):
    def get_by_digest(self, token_digest: str) -> AccountLifecycleProof | None: ...
    def get_by_id(self, proof_id: UUID) -> AccountLifecycleProof | None: ...
    def replace(self, proof: AccountLifecycleProof) -> AccountLifecycleProof: ...
    def consume(self, proof_id: UUID, now: datetime) -> bool: ...
    def supersede_for_account(
        self, account_id: UUID, purpose: ProofPurpose
    ) -> None: ...
