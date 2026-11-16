"""PostgreSQL adapter for immutable Business-scoped command receipts."""

from typing import Any
from uuid import UUID

from huginn.management.domain.entities.command_receipt import CommandReceipt
from huginn.management.domain.errors.errors import ConflictError, ValidationDomainError
from huginn.management.domain.value_objects.command_identity import CommandIdentity
from huginn.management.domain.value_objects.json_snapshot import JsonSnapshot
from huginn.management.persistence.contracts.database import (
    DatabaseSession,
    JsonParameter,
)
from huginn.management.persistence.contracts.repositories.command_receipt import (
    CommandReceiptRepository,
)
from huginn.management.persistence.errors.database import IntegrityError


class PostgresCommandReceiptRepository(CommandReceiptRepository):
    _columns = (
        "business_id,idempotency_key,scope,payload_fingerprint,resource_kind,"
        "resource_id,resource_version,result_snapshot,recorded_at"
    )

    def __init__(self, connection: DatabaseSession) -> None:
        self.connection = connection

    @staticmethod
    def _map(row: tuple[Any, ...]) -> CommandReceipt:
        return CommandReceipt(
            business_id=row[0],
            scope=row[2],
            identity=CommandIdentity(row[1], row[3]),
            resource_kind=row[4],
            resource_id=row[5],
            resource_version=row[6],
            result_snapshot=JsonSnapshot(row[7]),
            recorded_at=row[8],
        )

    def get_by_key(
        self, business_id: UUID, idempotency_key: str
    ) -> CommandReceipt | None:
        row = self.connection.execute(
            f"SELECT {self._columns} FROM operational.command_receipts "
            "WHERE business_id=%s AND idempotency_key=%s",
            (business_id, idempotency_key),
        ).fetchone()
        return self._map(row) if row else None

    def record(self, receipt: CommandReceipt) -> CommandReceipt:
        try:
            row = self.connection.execute(
                f"INSERT INTO operational.command_receipts ({self._columns}) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (business_id,idempotency_key) DO NOTHING "
                f"RETURNING {self._columns}",
                (
                    receipt.business_id,
                    receipt.identity.key,
                    receipt.scope,
                    receipt.identity.payload_fingerprint,
                    receipt.resource_kind,
                    receipt.resource_id,
                    receipt.resource_version,
                    JsonParameter(receipt.result_snapshot.to_json_object()),
                    receipt.recorded_at,
                ),
            ).fetchone()
        except IntegrityError as exc:
            if exc.sqlstate == "23505":
                raise ConflictError(
                    "Command request key already has a receipt"
                ) from exc
            raise ValidationDomainError(
                "Command receipt violates a persistence constraint"
            ) from exc
        if row:
            return self._map(row)
        existing = self.get_by_key(receipt.business_id, receipt.identity.key)
        if existing is None:
            raise ConflictError("Command receipt was concurrently changed")
        raise ConflictError("Command request key already has a receipt")
