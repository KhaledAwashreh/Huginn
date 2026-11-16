"""PostgreSQL adapter for transactional offer-cycle claims and audit events."""

import hashlib
from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from huginn.management.domain.entities.offer_cycle import OfferCycle
from huginn.management.domain.errors.errors import ConflictError, ValidationDomainError
from huginn.management.domain.value_objects.accepted_offer_cadence import (
    AcceptedOfferCadence,
)
from huginn.management.domain.value_objects.offer_cycle_status import OfferCycleStatus
from huginn.management.persistence.contracts.database import (
    DatabaseSession,
    JsonParameter,
)
from huginn.management.persistence.contracts.repositories.offer_cycle import (
    OfferCycleRepository,
)
from huginn.management.persistence.errors.database import IntegrityError


class PostgresOfferCycleRepository(OfferCycleRepository):
    _columns = (
        "id,business_id,company_id,recommendation_id,selected_revision_id,"
        "idempotency_key,payload_fingerprint,status,created_at,updated_at,"
        "claim_token,lease_expires_at,sending_started_at,settled_at,presented_at"
    )

    def __init__(self, connection: DatabaseSession) -> None:
        self.connection = connection

    @staticmethod
    def _map(row: tuple[Any, ...]) -> OfferCycle:
        return OfferCycle(
            id=row[0],
            business_id=row[1],
            company_id=row[2],
            recommendation_id=row[3],
            selected_revision_id=row[4],
            idempotency_key=row[5],
            payload_fingerprint=row[6],
            status=OfferCycleStatus(row[7]),
            created_at=row[8],
            updated_at=row[9],
            claim_token=row[10],
            lease_expires_at=row[11],
            sending_started_at=row[12],
            settled_at=row[13],
            presented_at=row[14],
        )

    def _one(self, query: str, params: tuple[Any, ...]) -> tuple[Any, ...] | None:
        return self.connection.execute(query, params).fetchone()

    def get_by_request_key(
        self, business_id: UUID, idempotency_key: str
    ) -> OfferCycle | None:
        row = self._one(
            f"SELECT {self._columns} FROM operational.offer_cycles "
            "WHERE business_id=%s AND idempotency_key=%s",
            (business_id, idempotency_key),
        )
        return self._map(row) if row else None

    def get_pending(self, business_id: UUID, company_id: UUID) -> OfferCycle | None:
        row = self._one(
            f"SELECT {self._columns} FROM operational.offer_cycles "
            "WHERE business_id=%s AND company_id=%s "
            "AND status IN ('preparing','sending','unknown') "
            "ORDER BY created_at,id LIMIT 1",
            (business_id, company_id),
        )
        return self._map(row) if row else None

    def list_expired_preparing(
        self,
        business_id: UUID,
        at: datetime,
        limit: int = 100,
        company_ids: tuple[UUID, ...] | None = None,
    ) -> tuple[OfferCycle, ...]:
        if limit < 1 or limit > 100:
            raise ValidationDomainError(
                "Expired offer cleanup limit must be between 1 and 100"
            )
        if company_ids is not None and len(company_ids) > 100:
            raise ValidationDomainError(
                "Expired offer cleanup may target at most 100 Companies"
            )
        if company_ids is not None and not company_ids:
            return ()
        company_filter = ""
        params: tuple[Any, ...] = (business_id, at)
        if company_ids is not None:
            company_filter = " AND company_id=ANY(%s)"
            params += (list(company_ids),)
        rows = self.connection.execute(
            f"SELECT {self._columns} FROM operational.offer_cycles "
            "WHERE business_id=%s AND status='preparing' AND lease_expires_at<=%s"
            + company_filter
            + " ORDER BY company_id,id LIMIT %s",
            params + (limit,),
        ).fetchall()
        return tuple(self._map(row) for row in rows)

    def get_owned(
        self, business_id: UUID, company_id: UUID, cycle_id: UUID
    ) -> OfferCycle | None:
        row = self._one(
            f"SELECT {self._columns} FROM operational.offer_cycles "
            "WHERE business_id=%s AND company_id=%s AND id=%s",
            (business_id, company_id, cycle_id),
        )
        return self._map(row) if row else None

    def get_by_id(self, business_id: UUID, cycle_id: UUID) -> OfferCycle | None:
        row = self._one(
            f"SELECT {self._columns} FROM operational.offer_cycles "
            "WHERE business_id=%s AND id=%s",
            (business_id, cycle_id),
        )
        return self._map(row) if row else None

    def get_confirmed_app_presentation(
        self,
        business_id: UUID,
        company_id: UUID,
        cycle_id: UUID,
        actor_user_id: UUID,
        claim_token: str,
    ) -> OfferCycle | None:
        return self._confirmed_app_replay(
            business_id,
            company_id,
            cycle_id,
            actor_user_id,
            _token_fingerprint(claim_token),
        )

    def acquire_preparing(
        self,
        cycle: OfferCycle,
        *,
        now: datetime,
        lease_expires_at: datetime,
        claim_token: str,
    ) -> OfferCycle:
        try:
            row = self._one(
                f"INSERT INTO operational.offer_cycles ({self._columns}) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,'preparing',%s,%s,%s,%s,NULL,NULL,NULL) "
                f"RETURNING {self._columns}",
                (
                    cycle.id,
                    cycle.business_id,
                    cycle.company_id,
                    cycle.recommendation_id,
                    cycle.selected_revision_id,
                    cycle.idempotency_key,
                    cycle.payload_fingerprint,
                    now,
                    now,
                    claim_token,
                    lease_expires_at,
                ),
            )
        except IntegrityError as exc:
            raise self._translate_conflict(exc) from exc
        assert row is not None
        result = self._map(row)
        self._event(
            result,
            "preparing_acquired",
            recorded_at=now,
            payload={
                "lease_expires_at": lease_expires_at.isoformat(),
                "payload_fingerprint": cycle.payload_fingerprint,
                "claim_token_fingerprint": _token_fingerprint(claim_token),
            },
        )
        return result

    def confirm_preparing(
        self,
        business_id: UUID,
        company_id: UUID,
        cycle_id: UUID,
        claim_token: str,
        confirmed_at: datetime,
        accepted_cadence: AcceptedOfferCadence,
        actor_user_id: UUID,
    ) -> OfferCycle:
        _validate_cadence_time(accepted_cadence, confirmed_at)
        row = self._one(
            "UPDATE operational.offer_cycles SET status='confirmed',updated_at=%s,"
            "claim_token=NULL,lease_expires_at=NULL,settled_at=%s,presented_at=%s "
            "WHERE business_id=%s AND company_id=%s AND id=%s AND claim_token=%s "
            "AND status='preparing' AND lease_expires_at>%s "
            f"RETURNING {self._columns}",
            (
                confirmed_at,
                confirmed_at,
                confirmed_at,
                business_id,
                company_id,
                cycle_id,
                claim_token,
                confirmed_at,
            ),
        )
        if row is None:
            replay = self._confirmed_app_replay(
                business_id,
                company_id,
                cycle_id,
                actor_user_id,
                _token_fingerprint(claim_token),
            )
            if replay is not None:
                return replay
            raise ConflictError("Offer cycle changed or is outside this scope")
        result = self._map(row)
        self._event(
            result,
            "preparing_confirmed",
            actor_user_id=actor_user_id,
            outcome="confirmed",
            presented_at=confirmed_at,
            recorded_at=confirmed_at,
            payload={
                **_cadence_payload(accepted_cadence),
                "claim_token_fingerprint": _token_fingerprint(claim_token),
            },
        )
        return result

    def mark_sending(
        self,
        business_id: UUID,
        company_id: UUID,
        cycle_id: UUID,
        claim_token: str,
        started_at: datetime,
        accepted_cadence: AcceptedOfferCadence,
    ) -> OfferCycle:
        _validate_cadence_time(accepted_cadence, started_at)
        row = self._transition(
            "UPDATE operational.offer_cycles SET status='sending',updated_at=%s,"
            "lease_expires_at=NULL,sending_started_at=%s "
            "WHERE business_id=%s AND company_id=%s AND id=%s AND claim_token=%s "
            "AND status='preparing' AND lease_expires_at>%s",
            (
                started_at,
                started_at,
                business_id,
                company_id,
                cycle_id,
                claim_token,
                started_at,
            ),
        )
        self._event(
            row,
            "sending_authorized",
            recorded_at=started_at,
            payload={
                **_cadence_payload(accepted_cadence),
                "claim_token_fingerprint": _token_fingerprint(claim_token),
            },
        )
        return row

    def accepted_cadence(
        self, business_id: UUID, company_id: UUID, cycle_id: UUID
    ) -> AcceptedOfferCadence | None:
        row = self._one(
            "SELECT payload,recorded_at FROM operational.offer_cycle_events "
            "WHERE business_id=%s AND company_id=%s AND offer_cycle_id=%s "
            "AND event_kind IN ('preparing_confirmed','sending_authorized') "
            "ORDER BY recorded_at DESC,id DESC LIMIT 1",
            (business_id, company_id, cycle_id),
        )
        if row is None:
            return None
        payload, recorded_at = row
        try:
            value = AcceptedOfferCadence(
                payload["repeat_interval_days"],
                datetime.fromisoformat(payload["preference_updated_at"]),
                datetime.fromisoformat(payload["accepted_at"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationDomainError(
                "Offer cadence audit event is incomplete"
            ) from exc
        if value.accepted_at != recorded_at:
            raise ValidationDomainError("Offer cadence acceptance time is inconsistent")
        return value

    def _confirmed_app_replay(
        self,
        business_id: UUID,
        company_id: UUID,
        cycle_id: UUID,
        actor_user_id: UUID,
        token_fingerprint: str,
    ) -> OfferCycle | None:
        row = self._one(
            f"SELECT {', '.join('cycle.' + column for column in self._columns.split(','))} "
            "FROM operational.offer_cycles cycle "
            "JOIN operational.offer_cycle_events event "
            "ON event.offer_cycle_id=cycle.id AND event.business_id=cycle.business_id "
            "AND event.company_id=cycle.company_id "
            "WHERE cycle.business_id=%s AND cycle.company_id=%s AND cycle.id=%s "
            "AND cycle.status='confirmed' AND event.event_kind='preparing_confirmed' "
            "AND event.actor_user_id=%s "
            "AND event.payload->>'claim_token_fingerprint'=%s",
            (
                business_id,
                company_id,
                cycle_id,
                actor_user_id,
                token_fingerprint,
            ),
        )
        return self._map(row) if row else None

    def abandon_preparing(
        self,
        business_id: UUID,
        company_id: UUID,
        cycle_id: UUID,
        claim_token: str,
        actor_user_id: UUID | None,
        reason: str,
        abandoned_at: datetime,
    ) -> OfferCycle:
        row = self._transition(
            "UPDATE operational.offer_cycles SET status='abandoned',updated_at=%s,"
            "claim_token=NULL,lease_expires_at=NULL,settled_at=%s "
            "WHERE business_id=%s AND company_id=%s AND id=%s AND claim_token=%s "
            "AND status='preparing'",
            (
                abandoned_at,
                abandoned_at,
                business_id,
                company_id,
                cycle_id,
                claim_token,
            ),
        )
        self._event(
            row,
            "preparing_abandoned",
            actor_user_id=actor_user_id,
            reason=reason,
            outcome="abandoned",
            recorded_at=abandoned_at,
        )
        return row

    def release_expired_preparing(
        self, business_id: UUID, company_id: UUID, cycle_id: UUID, now: datetime
    ) -> bool:
        row = self._one(
            "UPDATE operational.offer_cycles SET status='abandoned',updated_at=%s,"
            "claim_token=NULL,settled_at=%s,lease_expires_at=NULL "
            "WHERE business_id=%s AND company_id=%s AND id=%s "
            "AND status='preparing' AND lease_expires_at<=%s "
            f"RETURNING {self._columns}",
            (now, now, business_id, company_id, cycle_id, now),
        )
        if row is None:
            return False
        self._event(self._map(row), "preparing_expired", recorded_at=now)
        return True

    def settle_sending(
        self,
        business_id: UUID,
        company_id: UUID,
        cycle_id: UUID,
        claim_token: str,
        outcome: Literal["confirmed", "pre_send_failed", "unknown"],
        settled_at: datetime,
        presented_at: datetime | None = None,
        *,
        actor_user_id: UUID | None = None,
        reason: str | None = None,
    ) -> OfferCycle:
        if (actor_user_id is not None or reason is not None) and (
            outcome != "unknown"
            or not isinstance(actor_user_id, UUID)
            or type(reason) is not str
            or not reason.strip()
        ):
            raise ValidationDomainError(
                "Stopped sender observation requires an actor and reason"
            )
        if outcome == "confirmed":
            if presented_at is None:
                raise ValidationDomainError("Confirmed delivery requires handoff time")
            status = "confirmed"
            event_kind = "sending_confirmed"
        elif outcome == "pre_send_failed":
            status = "abandoned"
            event_kind = "sending_failed"
            presented_at = None
        elif outcome == "unknown":
            status = "unknown"
            event_kind = "sending_unknown"
            presented_at = None
        else:
            raise ValidationDomainError("Invalid sending settlement outcome")
        row = self._transition(
            "UPDATE operational.offer_cycles SET status=%s,updated_at=%s,"
            "settled_at=%s,presented_at=%s "
            "WHERE business_id=%s AND company_id=%s AND id=%s AND claim_token=%s "
            "AND status='sending'",
            (
                status,
                settled_at,
                settled_at,
                presented_at,
                business_id,
                company_id,
                cycle_id,
                claim_token,
            ),
        )
        self._event(
            row,
            event_kind,
            outcome=outcome,
            presented_at=presented_at,
            recorded_at=settled_at,
            actor_user_id=actor_user_id,
            reason=reason,
        )
        return row

    def resolve_unknown(
        self,
        business_id: UUID,
        company_id: UUID,
        cycle_id: UUID,
        actor_user_id: UUID,
        reason: str,
        outcome: Literal["confirmed", "abandoned"],
        presented_at: datetime | None,
        resolved_at: datetime,
    ) -> OfferCycle:
        if outcome not in {"confirmed", "abandoned"}:
            raise ValidationDomainError("Invalid Unknown recovery outcome")
        if (outcome == "confirmed") != (presented_at is not None):
            raise ValidationDomainError("Recovery handoff time must match outcome")
        row = self._transition(
            "UPDATE operational.offer_cycles SET status=%s,updated_at=%s,"
            "settled_at=%s,presented_at=%s "
            "WHERE business_id=%s AND company_id=%s AND id=%s AND status='unknown'",
            (
                outcome,
                resolved_at,
                resolved_at,
                presented_at,
                business_id,
                company_id,
                cycle_id,
            ),
        )
        self._event(
            row,
            "unknown_resolved",
            actor_user_id=actor_user_id,
            reason=reason,
            outcome=outcome,
            presented_at=presented_at,
            resolved_at=resolved_at,
            recorded_at=resolved_at,
        )
        return row

    def _transition(self, statement: str, params: tuple[Any, ...]) -> OfferCycle:
        row = self._one(statement + f" RETURNING {self._columns}", params)
        if row is None:
            raise ConflictError("Offer cycle changed or is outside this scope")
        return self._map(row)

    def _event(
        self,
        cycle: OfferCycle,
        event_kind: str,
        *,
        actor_user_id: UUID | None = None,
        reason: str | None = None,
        outcome: str | None = None,
        presented_at: datetime | None = None,
        resolved_at: datetime | None = None,
        recorded_at: datetime,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.connection.execute(
            "INSERT INTO operational.offer_cycle_events "
            "(id,offer_cycle_id,business_id,company_id,event_kind,actor_user_id,"
            "reason,outcome,presented_at,resolved_at,recorded_at,payload) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                uuid4(),
                cycle.id,
                cycle.business_id,
                cycle.company_id,
                event_kind,
                actor_user_id,
                reason,
                outcome,
                presented_at,
                resolved_at,
                recorded_at,
                JsonParameter(payload or {}),
            ),
        )

    @staticmethod
    def _translate_conflict(exc: IntegrityError) -> Exception:
        if exc.sqlstate == "23505":
            return ConflictError("Offer cycle request or company claim already exists")
        if exc.sqlstate == "23503":
            return ConflictError("Offer cycle recommendation is outside this Business")
        return ValidationDomainError("Offer cycle violates a persistence constraint")


def _token_fingerprint(claim_token: str) -> str:
    return hashlib.sha256(claim_token.encode("utf-8")).hexdigest()


def _cadence_payload(cadence: AcceptedOfferCadence) -> dict[str, Any]:
    return {
        "repeat_interval_days": cadence.repeat_interval_days,
        "preference_updated_at": cadence.preference_updated_at.isoformat(),
        "accepted_at": cadence.accepted_at.isoformat(),
    }


def _validate_cadence_time(
    cadence: AcceptedOfferCadence, transition_at: datetime
) -> None:
    if cadence.accepted_at != transition_at:
        raise ValidationDomainError(
            "Accepted cadence time must match offer transition time"
        )
