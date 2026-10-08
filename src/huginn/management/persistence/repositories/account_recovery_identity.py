"""PostgreSQL recovery identity repository."""

from datetime import datetime
from typing import Any
from uuid import UUID

from huginn.management.domain.entities.account_recovery_identity import (
    AccountRecoveryIdentity,
)
from huginn.management.persistence.contracts.repositories.account_recovery_identity import (
    AccountRecoveryIdentityRepository,
)
from huginn.management.persistence.errors.database import IntegrityError
from huginn.management.persistence.repositories.common import PostgresIdentityRepository
from huginn.management.persistence.row_models.account_recovery_identity import (
    AccountRecoveryIdentityRow,
)


class PostgresAccountRecoveryIdentityRepository(
    PostgresIdentityRepository, AccountRecoveryIdentityRepository
):
    """Persist verified and pending recovery addresses on the caller's transaction."""

    _columns = (
        "account_id, verification_required, pending_email, verified_email, "
        "verified_at, created_at, updated_at"
    )
    _row_fields = (
        "account_id",
        "verification_required",
        "pending_email",
        "verified_email",
        "verified_at",
        "created_at",
        "updated_at",
    )

    @classmethod
    def _map(cls, row: tuple[Any, ...]) -> AccountRecoveryIdentity:
        persisted = AccountRecoveryIdentityRow.model_validate(
            dict(zip(cls._row_fields, row, strict=True))
        )
        return AccountRecoveryIdentity(
            persisted.account_id,
            persisted.verification_required,
            persisted.pending_email,
            persisted.verified_email,
            persisted.verified_at,
            persisted.created_at,
            persisted.updated_at,
        )

    def get_by_account_id(self, account_id: UUID) -> AccountRecoveryIdentity | None:
        row = self._one(
            f"SELECT {self._columns} FROM operational.account_recovery_identity "
            "WHERE account_id = %s",
            (account_id,),
        )
        return self._map(row) if row else None

    def get_by_email(self, email: str) -> AccountRecoveryIdentity | None:
        row = self._one(
            f"SELECT {self._columns} FROM operational.account_recovery_identity "
            "WHERE lower(btrim(COALESCE(pending_email, verified_email))) = %s",
            (email.strip().lower(),),
        )
        return self._map(row) if row else None

    def create(
        self,
        account_id: UUID,
        *,
        verification_required: bool,
        pending_email: str | None = None,
    ) -> AccountRecoveryIdentity:
        try:
            row = self._write(
                "INSERT INTO operational.account_recovery_identity "
                "(account_id, verification_required, pending_email) "
                f"VALUES (%s, %s, %s) RETURNING {self._columns}",
                (account_id, verification_required, pending_email),
            )
        except IntegrityError as exc:
            raise self._translate(exc) from exc
        return self._map(row)

    def set_pending_email(
        self, account_id: UUID, email: str
    ) -> AccountRecoveryIdentity | None:
        try:
            row = self._one(
                "UPDATE operational.account_recovery_identity "
                "SET pending_email = %s, updated_at = clock_timestamp() "
                "WHERE account_id = %s AND verified_email IS NULL "
                f"RETURNING {self._columns}",
                (email, account_id),
            )
        except IntegrityError as exc:
            raise self._translate(exc) from exc
        return self._map(row) if row else None

    def verify_email(
        self, account_id: UUID, destination: str, now: datetime
    ) -> AccountRecoveryIdentity | None:
        try:
            row = self._one(
                "UPDATE operational.account_recovery_identity SET "
                "pending_email = NULL, verified_email = %s, "
                "verified_at = GREATEST(%s, clock_timestamp()), "
                "updated_at = GREATEST(%s, clock_timestamp()) "
                "WHERE account_id = %s AND pending_email = %s "
                "AND verified_email IS NULL "
                f"RETURNING {self._columns}",
                (destination, now, now, account_id, destination),
            )
        except IntegrityError as exc:
            raise self._translate(exc) from exc
        return self._map(row) if row else None
