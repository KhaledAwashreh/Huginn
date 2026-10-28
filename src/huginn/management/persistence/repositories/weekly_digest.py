"""Weekly delivery persistence on the caller's transaction; architecture section 9."""

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid4

from huginn.management.application.protocols.weekly_digest_repository import (
    WeeklyDigestRepository,
)
from huginn.management.application.read_models.digest_subscription import (
    DigestSubscription,
)
from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.persistence.contracts.database import (
    DatabaseSession,
    JsonParameter,
)

_ELIGIBLE = """FROM operational.weekly_digest_subscriptions d
    JOIN operational.users u ON u.id=d.user_id
    JOIN operational.accounts a ON a.id=u.account_id
    JOIN operational.account_recovery_identity r ON r.account_id=a.id
    WHERE d.enabled AND a.status='active' AND r.verified_email IS NOT NULL
      AND r.verified_at IS NOT NULL AND EXISTS (
        SELECT 1 FROM operational.client_discovery_strategies s
        JOIN operational.service_offerings o ON o.id=s.service_offering_id AND o.user_id=s.user_id
        JOIN operational.ideal_client_profiles i ON i.id=s.ideal_client_profile_id AND i.user_id=s.user_id
        WHERE s.user_id=u.id AND s.is_active)"""


def _aware(now: datetime) -> None:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValidationDomainError("Digest time must include a timezone")


class PostgresWeeklyDigestRepository(WeeklyDigestRepository):
    def __init__(self, connection: DatabaseSession) -> None:
        self.connection = connection

    def subscribe(self, user_id: UUID, now: datetime) -> None:
        _aware(now)
        row = self.connection.execute(
            """INSERT INTO operational.weekly_digest_subscriptions(user_id,enabled,updated_at)
            SELECT u.id,true,%s FROM operational.users u
            JOIN operational.accounts a ON a.id=u.account_id
            JOIN operational.account_recovery_identity r ON r.account_id=a.id
            WHERE u.id=%s AND a.status='active' AND r.verified_email IS NOT NULL AND r.verified_at IS NOT NULL
              AND EXISTS (SELECT 1 FROM operational.client_discovery_strategies s
                JOIN operational.service_offerings o ON o.id=s.service_offering_id AND o.user_id=s.user_id
                JOIN operational.ideal_client_profiles i ON i.id=s.ideal_client_profile_id AND i.user_id=s.user_id
                WHERE s.user_id=u.id AND s.is_active)
            ON CONFLICT (user_id) DO UPDATE SET enabled=true,updated_at=EXCLUDED.updated_at RETURNING user_id""",
            (now, user_id),
        ).fetchone()
        if row is None:
            raise ValidationDomainError(
                "Digest requires an active account, verified email and active owned strategy"
            )

    def unsubscribe(self, user_id: UUID) -> None:
        self.connection.execute(
            "UPDATE operational.weekly_digest_subscriptions SET enabled=false,updated_at=clock_timestamp() WHERE user_id=%s",
            (user_id,),
        )

    def subscriptions(self, limit: int) -> tuple[DigestSubscription, ...]:
        if not 1 <= limit <= 10000:
            raise ValidationDomainError(
                "Digest subscription limit must be between 1 and 10000"
            )
        rows = self.connection.execute(
            "SELECT d.user_id,r.verified_email "
            + _ELIGIBLE
            + " ORDER BY (SELECT max(created_at) FROM operational.weekly_digest_deliveries h WHERE h.user_id=d.user_id) NULLS FIRST,d.user_id LIMIT %s",
            (limit,),
        ).fetchall()
        return tuple(DigestSubscription(*row) for row in rows)

    def eligible(self, subscription: DigestSubscription) -> bool:
        return (
            self.connection.execute(
                "SELECT 1 " + _ELIGIBLE + " AND d.user_id=%s AND r.verified_email=%s",
                (
                    subscription.user_id,
                    subscription.recipient,
                ),
            ).fetchone()
            is not None
        )

    def reserve(
        self, user_id: UUID, week_start: date, now: datetime, daily_limit: int
    ) -> UUID | None:
        _aware(now)
        if daily_limit < 1 or week_start.weekday() != 0:
            raise ValidationDomainError(
                "Digest requires a positive daily limit and Monday week start"
            )
        # Serialize budget accounting across all workers, not only this user.
        self.connection.execute("SELECT pg_advisory_xact_lock(731094821)")
        start = datetime.combine(now.astimezone(UTC).date(), time.min, UTC)
        delivery = uuid4()
        row = self.connection.execute(
            """INSERT INTO operational.weekly_digest_deliveries(id,user_id,week_start,created_at)
            SELECT %s,%s,%s,%s WHERE EXISTS (SELECT 1 """
            + _ELIGIBLE
            + """ AND d.user_id=%s)
            AND (SELECT count(*) FROM operational.weekly_digest_deliveries
                WHERE created_at >= %s AND created_at < %s) < %s
            ON CONFLICT (user_id,week_start) DO NOTHING RETURNING id""",
            (
                delivery,
                user_id,
                week_start,
                now,
                user_id,
                start,
                start + timedelta(days=1),
                daily_limit,
            ),
        ).fetchone()
        return row[0] if row else None

    def previous_companies(self, user_id: UUID) -> frozenset[UUID]:
        rows = self.connection.execute(
            "SELECT company_ids FROM operational.weekly_digest_deliveries WHERE user_id=%s AND state IN ('sending','sent','unknown')",
            (user_id,),
        ).fetchall()
        return frozenset(UUID(company) for row in rows for company in row[0])

    def prepare(
        self,
        delivery_id: UUID,
        batch_id: UUID,
        recipient: str,
        subject: str,
        body: str,
        company_ids: tuple[UUID, ...],
    ) -> None:
        row = self.connection.execute(
            """UPDATE operational.weekly_digest_deliveries d SET state='sending',batch_id=%s,
            recipient=%s,subject=%s,body=%s,company_ids=%s
            WHERE d.id=%s AND d.state='preparing' AND EXISTS (
                SELECT 1 FROM operational.recommendation_batches b
                JOIN operational.weekly_digest_subscriptions s ON s.user_id=d.user_id
                WHERE b.id=%s AND b.user_id=d.user_id AND s.enabled AND b.snapshot->'batch'->>'kind'='weekly'
                  AND NOT EXISTS (
                    SELECT 1 FROM jsonb_array_elements(b.snapshot->'batch'->'items') item
                    WHERE NOT EXISTS (SELECT 1 FROM operational.client_discovery_strategies strategy
                      WHERE strategy.user_id=d.user_id AND strategy.is_active
                        AND strategy.id=(item->'strategies'->0->>'id')::uuid))
            ) RETURNING d.id""",
            (
                batch_id,
                recipient,
                subject,
                body,
                JsonParameter([str(item) for item in company_ids]),
                delivery_id,
                batch_id,
            ),
        ).fetchone()
        if row is None:
            raise ValidationDomainError(
                "Digest cannot be prepared from this owned batch or delivery state"
            )

    def settle(self, delivery_id: UUID, state: str, now: datetime) -> None:
        _aware(now)
        allowed = {
            "sent": "sending",
            "unknown": "sending",
            "empty": "preparing",
            "failed": "preparing",
            "suppressed": "preparing",
        }
        if state not in allowed:
            raise ValidationDomainError("Invalid digest settlement state")
        row = self.connection.execute(
            "UPDATE operational.weekly_digest_deliveries SET state=%s,settled_at=%s WHERE id=%s AND state=%s RETURNING id",
            (state, now, delivery_id, allowed[state]),
        ).fetchone()
        if row is None:
            raise ValidationDomainError(
                "Digest delivery is already settled or has an incompatible state"
            )
