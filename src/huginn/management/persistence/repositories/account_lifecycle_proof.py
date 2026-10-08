"""PostgreSQL purpose-bound lifecycle proof repository."""

from datetime import datetime
from typing import Any
from uuid import UUID

from huginn.management.domain.entities.account_lifecycle_proof import (
    AccountLifecycleProof,
)
from huginn.management.domain.value_objects.proof_purpose import ProofPurpose
from huginn.management.persistence.contracts.repositories.account_lifecycle_proof import (
    AccountLifecycleProofRepository,
)
from huginn.management.persistence.errors.database import IntegrityError
from huginn.management.persistence.repositories.common import PostgresIdentityRepository
from huginn.management.persistence.row_models.account_lifecycle_proof import (
    AccountLifecycleProofRow,
)


class PostgresAccountLifecycleProofRepository(
    PostgresIdentityRepository, AccountLifecycleProofRepository
):
    """Persist digest-only proofs on the caller's transaction."""

    _columns = (
        "id, account_id, token_digest, purpose, destination, expires_at, "
        "consumed_at, superseded, created_at"
    )
    _row_fields = (
        "id",
        "account_id",
        "token_digest",
        "purpose",
        "destination",
        "expires_at",
        "consumed_at",
        "superseded",
        "created_at",
    )

    @classmethod
    def _map(cls, row: tuple[Any, ...]) -> AccountLifecycleProof:
        persisted = AccountLifecycleProofRow.model_validate(
            dict(zip(cls._row_fields, row, strict=True))
        )
        return AccountLifecycleProof(
            persisted.id,
            persisted.account_id,
            persisted.token_digest,
            ProofPurpose(persisted.purpose),
            persisted.destination,
            persisted.expires_at,
            persisted.consumed_at,
            persisted.superseded,
            persisted.created_at,
        )

    def get_by_digest(self, token_digest: str) -> AccountLifecycleProof | None:
        row = self._one(
            f"SELECT {self._columns} FROM operational.account_lifecycle_proofs "
            "WHERE token_digest = %s",
            (token_digest,),
        )
        return self._map(row) if row else None

    def get_by_id(self, proof_id: UUID) -> AccountLifecycleProof | None:
        row = self._one(
            f"SELECT {self._columns} FROM operational.account_lifecycle_proofs "
            "WHERE id = %s",
            (proof_id,),
        )
        return self._map(row) if row else None

    def replace(self, proof: AccountLifecycleProof) -> AccountLifecycleProof:
        try:
            self._one(
                "UPDATE operational.account_lifecycle_proofs SET superseded = true "
                "WHERE account_id = %s AND purpose = %s AND consumed_at IS NULL "
                "AND superseded = false RETURNING id",
                (proof.account_id, proof.purpose.value),
            )
            row = self._write(
                "INSERT INTO operational.account_lifecycle_proofs "
                "(id, account_id, token_digest, purpose, destination, expires_at, "
                "consumed_at, superseded, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                f"RETURNING {self._columns}",
                (
                    proof.id,
                    proof.account_id,
                    proof.token_digest,
                    proof.purpose.value,
                    proof.destination,
                    proof.expires_at,
                    proof.consumed_at,
                    proof.superseded,
                    proof.created_at,
                ),
            )
        except IntegrityError as exc:
            raise self._translate(exc) from exc
        return self._map(row)

    def consume(self, proof_id: UUID, now: datetime) -> bool:
        row = self._one(
            "UPDATE operational.account_lifecycle_proofs "
            "SET consumed_at = GREATEST(%s, clock_timestamp()) "
            "WHERE id = %s AND consumed_at IS NULL AND superseded = false "
            "AND expires_at > GREATEST(%s, clock_timestamp()) RETURNING id",
            (now, proof_id, now),
        )
        return row is not None

    def supersede_for_account(self, account_id: UUID, purpose: ProofPurpose) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "UPDATE operational.account_lifecycle_proofs SET superseded = true "
                "WHERE account_id = %s AND purpose = %s "
                "AND consumed_at IS NULL AND superseded = false",
                (account_id, purpose.value),
            )
