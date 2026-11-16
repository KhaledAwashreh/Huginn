from datetime import UTC, datetime
from uuid import UUID

from huginn.management.application.protocols.digest_subscription_access import (
    DigestSubscriptionAccess,
)
from huginn.management.application.read_models.digest_subscription import (
    DigestSubscription,
)
from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.persistence.contracts.database import DatabaseSession

_ELIGIBLE = """FROM operational.weekly_digest_subscriptions d
JOIN operational.businesses b ON b.id=d.business_id
JOIN operational.users u ON u.id=b.owner_user_id
JOIN operational.accounts a ON a.id=u.account_id
JOIN operational.account_recovery_identity r ON r.account_id=a.id
WHERE d.enabled AND a.status='active'
  AND r.verified_email IS NOT NULL AND r.verified_at IS NOT NULL
  AND EXISTS (
    SELECT 1 FROM operational.client_discovery_strategies s
    JOIN operational.service_offerings o
      ON o.id=s.service_offering_id AND o.business_id=s.business_id
    JOIN operational.ideal_client_profiles i
      ON i.id=s.ideal_client_profile_id AND i.business_id=s.business_id
    WHERE s.business_id=b.id AND s.is_active
  )"""


class PostgresDigestSubscriptionAccess(DigestSubscriptionAccess):
    def __init__(self, connection: DatabaseSession) -> None:
        self.connection = connection

    def list_eligible(self, limit: int) -> tuple[DigestSubscription, ...]:
        if type(limit) is not int or not 1 <= limit <= 10000:
            raise ValidationDomainError(
                "Digest subscription limit must be between 1 and 10000"
            )
        rows = self.connection.execute(
            "SELECT b.id,u.id,r.verified_email,d.updated_at "
            + _ELIGIBLE
            + " ORDER BY (SELECT max(created_at) "
            "FROM operational.weekly_digest_deliveries h "
            "WHERE h.business_id=d.business_id) NULLS FIRST,d.business_id LIMIT %s",
            (limit,),
        ).fetchall()
        return tuple(_subscription(row) for row in rows)

    def get_for_business(self, business_id: UUID) -> DigestSubscription | None:
        _business_id(business_id)
        row = self.connection.execute(
            "SELECT b.id,u.id,r.verified_email,d.updated_at "
            + _ELIGIBLE
            + " AND b.id=%s",
            (business_id,),
        ).fetchone()
        return _subscription(row) if row is not None else None

    def get_for_authorization(self, business_id: UUID) -> DigestSubscription | None:
        _business_id(business_id)
        row = self.connection.execute(
            "SELECT b.id,u.id,r.verified_email,d.updated_at "
            + _ELIGIBLE
            + " AND b.id=%s FOR UPDATE OF d,a,r",
            (business_id,),
        ).fetchone()
        return _subscription(row) if row is not None else None

    def subscribe(self, actor_user_id: UUID, business_id: UUID, now: datetime) -> None:
        _owner_ids(actor_user_id, business_id)
        now = _aware_utc(now)
        row = self.connection.execute(
            """INSERT INTO operational.weekly_digest_subscriptions
                (business_id,enabled,updated_at)
            SELECT b.id,true,%s
            FROM operational.businesses b
            JOIN operational.users u ON u.id=b.owner_user_id
            JOIN operational.accounts a ON a.id=u.account_id
            JOIN operational.account_recovery_identity r ON r.account_id=a.id
            WHERE b.id=%s AND u.id=%s AND a.status='active'
              AND r.verified_email IS NOT NULL AND r.verified_at IS NOT NULL
              AND EXISTS (
                SELECT 1 FROM operational.client_discovery_strategies s
                JOIN operational.service_offerings o
                  ON o.id=s.service_offering_id AND o.business_id=s.business_id
                JOIN operational.ideal_client_profiles i
                  ON i.id=s.ideal_client_profile_id AND i.business_id=s.business_id
                WHERE s.business_id=b.id AND s.is_active
              )
            ON CONFLICT (business_id) DO UPDATE
              SET enabled=true,
                  updated_at=GREATEST(
                    EXCLUDED.updated_at,
                    operational.weekly_digest_subscriptions.updated_at
                      + interval '1 microsecond'
                  )
            RETURNING business_id""",
            (now, business_id, actor_user_id),
        ).fetchone()
        if row is None:
            raise ValidationDomainError(
                "Digest requires the Business owner, an active account, verified email and active owned strategy"
            )

    def get_for_opt_out(self, business_id: UUID) -> DigestSubscription | None:
        _business_id(business_id)
        row = self.connection.execute(
            """SELECT b.id,u.id,r.verified_email,d.updated_at
            FROM operational.weekly_digest_subscriptions d
            JOIN operational.businesses b ON b.id=d.business_id
            JOIN operational.users u ON u.id=b.owner_user_id
            JOIN operational.account_recovery_identity r ON r.account_id=u.account_id
            WHERE b.id=%s AND d.enabled AND r.verified_email IS NOT NULL
                AND r.verified_at IS NOT NULL
            FOR UPDATE OF d,r""",
            (business_id,),
        ).fetchone()
        return _subscription(row) if row is not None else None

    def unsubscribe(
        self, actor_user_id: UUID, business_id: UUID, now: datetime
    ) -> None:
        _owner_ids(actor_user_id, business_id)
        now = _aware_utc(now)
        owner = self.connection.execute(
            "SELECT 1 FROM operational.businesses WHERE id=%s AND owner_user_id=%s",
            (business_id, actor_user_id),
        ).fetchone()
        if owner is None:
            raise ValidationDomainError("Digest subscription is not owned by this User")
        self.connection.execute(
            "UPDATE operational.weekly_digest_subscriptions d "
            "SET enabled=false,updated_at=GREATEST(%s,d.updated_at+interval '1 microsecond') "
            "WHERE d.business_id=%s",
            (now, business_id),
        )


def _subscription(row: tuple) -> DigestSubscription:
    return DigestSubscription(
        business_id=row[0],
        user_id=row[1],
        recipient=row[2],
        updated_at=row[3],
    )


def _business_id(value: UUID) -> None:
    if not isinstance(value, UUID):
        raise ValidationDomainError("Business ID is required")


def _owner_ids(actor_user_id: UUID, business_id: UUID) -> None:
    if not isinstance(actor_user_id, UUID) or not isinstance(business_id, UUID):
        raise ValidationDomainError("Digest subscription owner IDs are required")


def _aware_utc(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValidationDomainError("Digest time must include a timezone")
    return value.astimezone(UTC)
