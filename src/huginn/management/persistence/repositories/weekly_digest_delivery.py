"""PostgreSQL adapter for weekly reservation lifecycle and audit events."""

from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal
from uuid import UUID, uuid4

from huginn.management.domain.entities.weekly_digest_delivery import (
    WeeklyDigestDelivery,
)
from huginn.management.domain.entities.weekly_digest_delivery_event import (
    WeeklyDigestDeliveryEvent,
)
from huginn.management.domain.errors.errors import (
    ConflictError,
    NotFoundError,
    ValidationDomainError,
)
from huginn.management.domain.value_objects.json_snapshot import JsonSnapshot
from huginn.management.persistence.contracts.database import (
    DatabaseSession,
    JsonParameter,
)
from huginn.management.persistence.contracts.repositories.weekly_digest_delivery import (
    DigestDeliveryOutcome,
    WeeklyDigestDeliveryRepository,
)
from huginn.management.persistence.errors.database import IntegrityError

_COLUMNS = (
    "id,business_id,recipient_user_id,week_start,created_at,state,version,"
    "current_content_id,sending_started_at,settled_at,accepted_at"
)
_EVENT_COLUMNS = (
    "id,delivery_id,business_id,delivery_version,event_kind,recorded_at,"
    "content_id,actor_user_id,reason,outcome,accepted_at,payload"
)
_DAILY_BUDGET_LOCK = 731094822


class PostgresWeeklyDigestDeliveryRepository(WeeklyDigestDeliveryRepository):
    def __init__(self, connection: DatabaseSession) -> None:
        self.connection = connection

    @staticmethod
    def _map(row: tuple[Any, ...]) -> WeeklyDigestDelivery:
        return WeeklyDigestDelivery(*row)

    @staticmethod
    def _map_event(row: tuple[Any, ...]) -> WeeklyDigestDeliveryEvent:
        return WeeklyDigestDeliveryEvent(
            id=row[0],
            delivery_id=row[1],
            business_id=row[2],
            delivery_version=row[3],
            event_kind=row[4],
            recorded_at=row[5],
            content_id=row[6],
            actor_user_id=row[7],
            reason=row[8],
            outcome=row[9],
            accepted_at=row[10],
            payload=JsonSnapshot(row[11]),
        )

    def reserve(
        self,
        business_id: UUID,
        recipient_user_id: UUID,
        week_start: date,
        now: datetime,
        daily_limit: int,
    ) -> WeeklyDigestDelivery | None:
        _ids(business_id, recipient_user_id)
        now = _aware_utc(now)
        if type(week_start) is not date or week_start.weekday() != 0:
            raise ValidationDomainError("Digest reservation requires Monday week start")
        if type(daily_limit) is not int or daily_limit < 1:
            raise ValidationDomainError("Digest daily limit must be positive")
        self.connection.execute(
            "SELECT pg_advisory_xact_lock(%s)", (_DAILY_BUDGET_LOCK,)
        )
        day_start = datetime.combine(now.date(), time.min, UTC)
        row = self.connection.execute(
            f"""INSERT INTO operational.weekly_digest_deliveries
                (id,business_id,recipient_user_id,week_start,created_at)
            SELECT %s,b.id,u.id,%s,%s
            FROM operational.businesses b
            JOIN operational.users u ON u.id=b.owner_user_id
            WHERE b.id=%s AND u.id=%s
              AND (SELECT count(*)
                   FROM operational.weekly_digest_deliveries d
                   WHERE d.created_at >= %s AND d.created_at < %s) < %s
            ON CONFLICT (business_id,week_start) DO NOTHING
            RETURNING {_COLUMNS}""",
            (
                uuid4(),
                week_start,
                now,
                business_id,
                recipient_user_id,
                day_start,
                day_start + timedelta(days=1),
                daily_limit,
            ),
        ).fetchone()
        if row is None:
            return None
        delivery = self._map(row)
        self._append_event(delivery, "reserved", now)
        return delivery

    def get_for_business(
        self, business_id: UUID, delivery_id: UUID
    ) -> WeeklyDigestDelivery | None:
        _ids(business_id, delivery_id)
        row = self.connection.execute(
            f"SELECT {_COLUMNS} FROM operational.weekly_digest_deliveries "
            "WHERE business_id=%s AND id=%s",
            (business_id, delivery_id),
        ).fetchone()
        return self._map(row) if row is not None else None

    def get_for_update(
        self, business_id: UUID, delivery_id: UUID
    ) -> WeeklyDigestDelivery | None:
        _ids(business_id, delivery_id)
        row = self.connection.execute(
            f"SELECT {_COLUMNS} FROM operational.weekly_digest_deliveries "
            "WHERE business_id=%s AND id=%s FOR UPDATE",
            (business_id, delivery_id),
        ).fetchone()
        return self._map(row) if row is not None else None

    def select_content(
        self,
        business_id: UUID,
        delivery_id: UUID,
        expected_version: int,
        content_id: UUID,
        selected_at: datetime,
    ) -> WeeklyDigestDelivery:
        _ids(business_id, delivery_id, content_id)
        _version(expected_version)
        selected_at = _aware_utc(selected_at)
        current = self._required_for_update(business_id, delivery_id)
        if (
            current.version != expected_version
            or current.state != "preparing"
            or selected_at < current.created_at
        ):
            raise ConflictError("Weekly reservation changed before content selection")
        selected_version = self.connection.execute(
            "SELECT version,created_at FROM operational.weekly_digest_contents "
            "WHERE id=%s AND delivery_id=%s AND business_id=%s",
            (content_id, delivery_id, business_id),
        ).fetchone()
        if selected_version is None:
            raise NotFoundError("Digest content is outside this reservation")
        if selected_at < selected_version[1]:
            raise ValidationDomainError("Content selection cannot precede its snapshot")
        previous_content_version = 0
        if current.current_content_id is not None:
            previous = self.connection.execute(
                "SELECT version FROM operational.weekly_digest_contents WHERE id=%s",
                (current.current_content_id,),
            ).fetchone()
            if previous is None:
                raise ValidationDomainError("Current digest content pointer is invalid")
            previous_content_version = previous[0]
        if selected_version[0] != previous_content_version + 1:
            raise ConflictError("Digest content selection requires the next version")
        row = self.connection.execute(
            f"UPDATE operational.weekly_digest_deliveries SET current_content_id=%s,"
            f"version=version+1 WHERE business_id=%s AND id=%s AND version=%s "
            f"AND state='preparing' RETURNING {_COLUMNS}",
            (content_id, business_id, delivery_id, expected_version),
        ).fetchone()
        if row is None:
            raise ConflictError("Weekly reservation changed before content selection")
        delivery = self._map(row)
        kind = (
            "content_prepared"
            if current.current_content_id is None
            else "content_replaced"
        )
        self._append_event(delivery, kind, selected_at, content_id=content_id)
        return delivery

    def authorize_sending(
        self,
        business_id: UUID,
        delivery_id: UUID,
        expected_version: int,
        expected_content_id: UUID,
        now: datetime,
    ) -> WeeklyDigestDelivery:
        _ids(business_id, delivery_id, expected_content_id)
        _version(expected_version)
        now = _aware_utc(now)
        current = self._required_for_update(business_id, delivery_id)
        if (
            current.state != "preparing"
            or current.version != expected_version
            or current.current_content_id != expected_content_id
            or now < current.created_at
        ):
            raise ConflictError("Weekly reservation changed before send authorization")
        row = self.connection.execute(
            f"UPDATE operational.weekly_digest_deliveries "
            "SET state='sending',version=version+1,sending_started_at=%s "
            "WHERE business_id=%s AND id=%s AND version=%s AND state='preparing' "
            "AND current_content_id=%s "
            f"RETURNING {_COLUMNS}",
            (now, business_id, delivery_id, expected_version, expected_content_id),
        ).fetchone()
        if row is None:
            raise ConflictError("Weekly reservation changed before send authorization")
        delivery = self._map(row)
        self._append_event(
            delivery, "sending_authorized", now, content_id=expected_content_id
        )
        return delivery

    def settle(
        self,
        business_id: UUID,
        delivery_id: UUID,
        expected_version: int,
        outcome: DigestDeliveryOutcome,
        recorded_at: datetime,
        accepted_at: datetime | None = None,
        reason: str | None = None,
    ) -> WeeklyDigestDelivery:
        _ids(business_id, delivery_id)
        _version(expected_version)
        recorded_at = _aware_utc(recorded_at)
        accepted_at = None if accepted_at is None else _aware_utc(accepted_at)
        _validate_outcome_time(outcome, recorded_at, accepted_at)
        if outcome not in {
            "sent",
            "unknown",
            "pre_send_failed",
            "preparation_failed",
            "empty",
            "suppressed",
        }:
            raise ValidationDomainError("Invalid weekly delivery outcome")
        current = self._required_for_update(business_id, delivery_id)
        requires_sending = outcome in {"sent", "unknown", "pre_send_failed"}
        expected_state = "sending" if requires_sending else "preparing"
        if current.version != expected_version or current.state != expected_state:
            raise ConflictError("Weekly reservation is already settled or changed")
        if recorded_at < (current.sending_started_at or current.created_at):
            raise ValidationDomainError("Settlement cannot precede reservation or send")
        if accepted_at is not None and (
            current.sending_started_at is None
            or accepted_at < current.sending_started_at
        ):
            raise ValidationDomainError(
                "SMTP acceptance cannot precede send authorization"
            )
        if reason is not None and not isinstance(reason, str):
            raise ValidationDomainError("Digest settlement reason must be text")
        state, event_kind = {
            "sent": ("sent", "sent"),
            "unknown": ("unknown", "unknown"),
            "pre_send_failed": ("failed", "pre_send_failed"),
            "preparation_failed": ("failed", "preparation_failed"),
            "empty": ("empty", "empty"),
            "suppressed": ("suppressed", "suppressed"),
        }[outcome]
        row = self.connection.execute(
            f"UPDATE operational.weekly_digest_deliveries SET state=%s,version=version+1,"
            f"settled_at=%s,accepted_at=%s WHERE business_id=%s AND id=%s "
            f"AND version=%s AND state=%s RETURNING {_COLUMNS}",
            (
                state,
                recorded_at,
                accepted_at,
                business_id,
                delivery_id,
                expected_version,
                expected_state,
            ),
        ).fetchone()
        if row is None:
            raise ConflictError("Weekly reservation is already settled or changed")
        delivery = self._map(row)
        self._append_event(
            delivery,
            event_kind,
            recorded_at,
            content_id=current.current_content_id,
            reason=reason,
            accepted_at=accepted_at,
        )
        return delivery

    def resolve_unknown(
        self,
        business_id: UUID,
        delivery_id: UUID,
        expected_version: int,
        actor_user_id: UUID,
        reason: str,
        outcome: Literal["sent", "failed"],
        recorded_at: datetime,
        accepted_at: datetime | None = None,
    ) -> WeeklyDigestDelivery:
        _ids(business_id, delivery_id, actor_user_id)
        _version(expected_version)
        recorded_at = _aware_utc(recorded_at)
        accepted_at = None if accepted_at is None else _aware_utc(accepted_at)
        if type(reason) is not str or not reason.strip():
            raise ValidationDomainError("Unknown recovery requires an actor reason")
        if outcome not in {"sent", "failed"}:
            raise ValidationDomainError(
                "Unknown recovery outcome must be sent or failed"
            )
        _validate_outcome_time(outcome, recorded_at, accepted_at)
        if outcome == "failed" and accepted_at is not None:
            raise ValidationDomainError("Failed recovery cannot record SMTP acceptance")
        if outcome == "sent" and accepted_at is None:
            raise ValidationDomainError("Sent recovery requires actual acceptance time")
        current = self._required_for_update(business_id, delivery_id)
        if current.version != expected_version or current.state != "unknown":
            raise ConflictError(
                "Weekly reservation is not the expected Unknown version"
            )
        if current.settled_at is not None and recorded_at < current.settled_at:
            raise ValidationDomainError(
                "Unknown recovery cannot precede its observation"
            )
        if accepted_at is not None and (
            current.sending_started_at is None
            or accepted_at < current.sending_started_at
        ):
            raise ValidationDomainError(
                "SMTP acceptance cannot precede send authorization"
            )
        owner = self.connection.execute(
            "SELECT 1 FROM operational.businesses WHERE id=%s AND owner_user_id=%s",
            (business_id, actor_user_id),
        ).fetchone()
        if owner is None:
            raise ConflictError("Unknown recovery actor does not own this Business")
        state = outcome
        row = self.connection.execute(
            f"UPDATE operational.weekly_digest_deliveries SET state=%s,version=version+1,"
            f"settled_at=%s,accepted_at=%s WHERE business_id=%s AND id=%s "
            f"AND version=%s AND state='unknown' RETURNING {_COLUMNS}",
            (
                state,
                recorded_at,
                accepted_at,
                business_id,
                delivery_id,
                expected_version,
            ),
        ).fetchone()
        if row is None:
            raise ConflictError(
                "Weekly reservation is not the expected Unknown version"
            )
        delivery = self._map(row)
        self._append_event(
            delivery,
            "unknown_resolved",
            recorded_at,
            content_id=current.current_content_id,
            actor_user_id=actor_user_id,
            reason=reason.strip(),
            outcome=outcome,
            accepted_at=accepted_at,
        )
        return delivery

    def list_events(
        self, business_id: UUID, delivery_id: UUID
    ) -> tuple[WeeklyDigestDeliveryEvent, ...]:
        _ids(business_id, delivery_id)
        rows = self.connection.execute(
            f"SELECT {_EVENT_COLUMNS} FROM operational.weekly_digest_delivery_events "
            "WHERE business_id=%s AND delivery_id=%s ORDER BY delivery_version",
            (business_id, delivery_id),
        ).fetchall()
        return tuple(self._map_event(row) for row in rows)

    def _required_for_update(
        self, business_id: UUID, delivery_id: UUID
    ) -> WeeklyDigestDelivery:
        current = self.get_for_update(business_id, delivery_id)
        if current is None:
            raise NotFoundError("Weekly delivery not found")
        return current

    def _append_event(
        self,
        delivery: WeeklyDigestDelivery,
        event_kind: str,
        recorded_at: datetime,
        *,
        content_id: UUID | None = None,
        actor_user_id: UUID | None = None,
        reason: str | None = None,
        outcome: Literal["sent", "failed"] | None = None,
        accepted_at: datetime | None = None,
    ) -> None:
        event = WeeklyDigestDeliveryEvent(
            id=uuid4(),
            delivery_id=delivery.id,
            business_id=delivery.business_id,
            delivery_version=delivery.version,
            event_kind=event_kind,
            recorded_at=recorded_at,
            content_id=content_id,
            actor_user_id=actor_user_id,
            reason=reason,
            outcome=outcome,
            accepted_at=accepted_at,
            payload=JsonSnapshot({}),
        )
        try:
            self.connection.execute(
                f"INSERT INTO operational.weekly_digest_delivery_events ({_EVENT_COLUMNS}) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    event.id,
                    event.delivery_id,
                    event.business_id,
                    event.delivery_version,
                    event.event_kind,
                    event.recorded_at,
                    event.content_id,
                    event.actor_user_id,
                    event.reason,
                    event.outcome,
                    event.accepted_at,
                    JsonParameter(event.payload.to_json_object()),
                ),
            )
        except IntegrityError as exc:
            if exc.sqlstate in {"23503", "23505", "23514"}:
                raise ConflictError(
                    "Weekly delivery event conflicts with lifecycle"
                ) from exc
            raise ValidationDomainError("Weekly delivery event is invalid") from exc


def _ids(*values: UUID) -> None:
    if any(not isinstance(value, UUID) for value in values):
        raise ValidationDomainError("Weekly delivery IDs must be UUIDs")


def _version(value: int) -> None:
    if type(value) is not int or value < 1:
        raise ValidationDomainError("Weekly delivery version must be positive")


def _aware_utc(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValidationDomainError("Weekly delivery time must include a timezone")
    return value.astimezone(UTC)


def _validate_outcome_time(
    outcome: str, recorded_at: datetime, accepted_at: datetime | None
) -> None:
    if outcome == "sent" and accepted_at is None:
        raise ValidationDomainError(
            "Sent delivery requires actual SMTP acceptance time"
        )
    if outcome != "sent" and accepted_at is not None:
        raise ValidationDomainError("Only confirmed delivery may record acceptance")
    if accepted_at is not None and accepted_at > recorded_at:
        raise ValidationDomainError("SMTP acceptance cannot follow recorded settlement")
