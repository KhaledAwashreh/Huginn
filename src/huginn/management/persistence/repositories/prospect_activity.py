"""PostgreSQL adapter for append-only, idempotent prospect activities."""

from typing import Any
from uuid import UUID

from huginn.management.domain.entities.prospect_activity import ProspectActivity
from huginn.management.domain.errors.errors import (
    ConflictError,
    NotFoundError,
    ValidationDomainError,
)
from huginn.management.domain.value_objects.activity_kind import ActivityKind
from huginn.management.domain.value_objects.command_identity import CommandIdentity
from huginn.management.domain.value_objects.json_snapshot import JsonSnapshot
from huginn.management.persistence.contracts.database import (
    DatabaseSession,
    JsonParameter,
)
from huginn.management.persistence.contracts.repositories.prospect_activity import (
    ProspectActivityRepository,
)
from huginn.management.persistence.errors.database import IntegrityError


class PostgresProspectActivityRepository(ProspectActivityRepository):
    _columns = (
        "id,business_id,prospect_id,actor_user_id,idempotency_key,"
        "payload_fingerprint,kind,occurred_at,recorded_at,payload,origin_id,correction_of_id"
    )

    def __init__(self, connection: DatabaseSession) -> None:
        self.connection = connection

    @staticmethod
    def _map(row: tuple[Any, ...]) -> ProspectActivity:
        return ProspectActivity(
            id=row[0],
            business_id=row[1],
            prospect_id=row[2],
            actor_user_id=row[3],
            kind=ActivityKind(row[6]),
            occurred_at=row[7],
            recorded_at=row[8],
            payload=JsonSnapshot(row[9]),
            correction_of_id=row[11],
        )

    def list_owned(
        self, business_id: UUID, prospect_id: UUID
    ) -> tuple[ProspectActivity, ...]:
        rows = self.connection.execute(
            f"SELECT {self._columns} FROM operational.prospect_activities "
            "WHERE business_id=%s AND prospect_id=%s ORDER BY recorded_at,id",
            (business_id, prospect_id),
        ).fetchall()
        return tuple(self._map(row) for row in rows)

    def append_once(
        self,
        business_id: UUID,
        prospect_id: UUID,
        identity: CommandIdentity,
        activity: ProspectActivity,
    ) -> ProspectActivity:
        if (activity.business_id, activity.prospect_id) != (business_id, prospect_id):
            raise ValidationDomainError("Activity identity does not match its scope")
        owned_prospect = self.connection.execute(
            "SELECT 1 FROM operational.prospects prospect "
            "JOIN operational.businesses business ON business.id=prospect.business_id "
            "AND business.owner_user_id=%s "
            "WHERE prospect.business_id=%s AND prospect.id=%s",
            (activity.actor_user_id, business_id, prospect_id),
        ).fetchone()
        if owned_prospect is None:
            raise ConflictError("Activity prospect is not owned by this actor")
        existing = self._by_request_key(business_id, identity.key)
        if existing:
            if existing[5] != identity.payload_fingerprint:
                raise ConflictError(
                    "Activity request key was used for a different payload"
                )
            return self._map(existing)
        origin_id = _origin_id(activity)
        if origin_id is not None:
            membership = self.connection.execute(
                "SELECT 1 FROM operational.prospect_origins "
                "WHERE id=%s AND business_id=%s AND prospect_id=%s",
                (origin_id, business_id, prospect_id),
            ).fetchone()
            if membership is None:
                raise NotFoundError("Prospect origin not found")
        try:
            row = self.connection.execute(
                f"INSERT INTO operational.prospect_activities ({self._columns}) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT DO NOTHING "
                f"RETURNING {self._columns}",
                (
                    activity.id,
                    business_id,
                    prospect_id,
                    activity.actor_user_id,
                    identity.key,
                    identity.payload_fingerprint,
                    activity.kind.value,
                    activity.occurred_at,
                    activity.recorded_at,
                    JsonParameter(activity.payload.to_json_object()),
                    origin_id,
                    activity.correction_of_id,
                ),
            ).fetchone()
        except IntegrityError as exc:
            if exc.sqlstate == "23505":
                raise ConflictError("Activity conflicts with existing history") from exc
            raise ValidationDomainError(
                "Activity violates a persistence constraint"
            ) from exc
        if row:
            return self._map(row)
        # A request key may have been claimed after the initial lookup while a
        # different exact-origin insert was waiting on its unique index.
        existing = self._by_request_key(business_id, identity.key)
        if existing is not None:
            if existing[5] != identity.payload_fingerprint:
                raise ConflictError(
                    "Activity request key was used for a different payload"
                )
            return self._map(existing)
        if origin_id is not None:
            existing = self.connection.execute(
                f"SELECT {self._columns} FROM operational.prospect_activities "
                "WHERE business_id=%s AND prospect_id=%s AND origin_id=%s",
                (business_id, prospect_id, origin_id),
            ).fetchone()
            if existing is not None:
                return self._map(existing)
        raise ConflictError("Activity was concurrently changed")

    def _by_request_key(self, business_id: UUID, key: str):
        return self.connection.execute(
            f"SELECT {self._columns} FROM operational.prospect_activities "
            "WHERE business_id=%s AND idempotency_key=%s",
            (business_id, key),
        ).fetchone()


def _origin_id(activity: ProspectActivity) -> UUID | None:
    if activity.kind.value != "prospect_saved":
        return None
    raw_id = activity.payload.value.get("origin_id")
    try:
        return UUID(str(raw_id))
    except (TypeError, ValueError) as exc:
        raise ValidationDomainError(
            "Saved activity must include its exact origin ID"
        ) from exc
