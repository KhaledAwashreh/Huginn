"""PostgreSQL durable lifecycle delivery bookkeeping."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from huginn.management.application.protocols.lifecycle_mail_outbox import (
    LifecycleMailOutboxRepository,
)
from huginn.management.application.read_models.lifecycle_mail_outbox import (
    LifecycleMailOutboxRecord,
)
from huginn.management.application.read_models.mail_delivery_claim import (
    MailDeliveryClaim,
)
from huginn.management.domain.value_objects.proof_purpose import ProofPurpose
from huginn.management.persistence.repositories.common import PostgresIdentityRepository
from huginn.management.persistence.row_models.lifecycle_mail_outbox import (
    LifecycleMailOutboxRow,
)


class PostgresLifecycleMailOutboxRepository(
    PostgresIdentityRepository, LifecycleMailOutboxRepository
):
    """Claim and settle on the caller's short transaction; see lifecycle design §4."""

    _row_fields = (
        "id",
        "account_id",
        "purpose",
        "proof_id",
        "encrypted_payload",
        "attempt_count",
        "next_attempt_at",
        "state",
        "failure_code",
        "claim_token",
        "claimed_at",
        "lease_until",
        "created_at",
        "updated_at",
        "sent_at",
    )

    @classmethod
    def _claim(cls, row: tuple[Any, ...]) -> MailDeliveryClaim:
        persisted = LifecycleMailOutboxRow.model_validate(
            dict(zip(cls._row_fields, row, strict=True))
        )
        assert persisted.encrypted_payload is not None
        assert persisted.claim_token is not None
        assert persisted.lease_until is not None
        return MailDeliveryClaim(
            persisted.id,
            persisted.account_id,
            persisted.proof_id,
            persisted.purpose,
            persisted.encrypted_payload,
            persisted.claim_token,
            persisted.attempt_count,
            persisted.lease_until,
        )

    def enqueue(self, record: LifecycleMailOutboxRecord) -> None:
        self._write(
            "INSERT INTO operational.lifecycle_mail_outbox "
            "(id,account_id,proof_id,purpose,encrypted_payload,next_attempt_at) "
            "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
            (
                record.id,
                record.account_id,
                record.proof_id,
                record.purpose,
                record.encrypted_payload,
                record.next_attempt_at,
            ),
        )

    def last_enqueued_at(
        self, account_id: UUID, purpose: ProofPurpose
    ) -> datetime | None:
        row = self._one(
            "SELECT max(created_at) FROM operational.lifecycle_mail_outbox "
            "WHERE account_id=%s AND purpose=%s",
            (account_id, purpose.value),
        )
        return row[0] if row else None

    def claim_due(
        self, now: datetime, *, lease_seconds: int, max_attempts: int
    ) -> MailDeliveryClaim | None:
        if not 1 <= max_attempts <= 5 or lease_seconds <= 0:
            raise ValueError("invalid lifecycle mail claim policy")
        # Skip live claims, including expired proofs still owned by a worker.
        # Locks are acquired before scrubbing so another claimant cannot race it.
        with self.connection.cursor() as cursor:
            cursor.execute(
                "WITH obsolete AS MATERIALIZED ("
                "SELECT o.id, p.expires_at <= GREATEST(%s,clock_timestamp()) AS expired "
                "FROM operational.lifecycle_mail_outbox o "
                "JOIN operational.account_lifecycle_proofs p ON p.id=o.proof_id "
                "WHERE (o.state='pending' OR "
                "(o.state='claimed' AND o.lease_until <= GREATEST(%s,clock_timestamp()))) "
                "AND (p.expires_at <= GREATEST(%s,clock_timestamp()) OR "
                "(o.attempt_count >= LEAST(%s,5) AND "
                "o.next_attempt_at <= GREATEST(%s,clock_timestamp()))) "
                "FOR UPDATE OF o SKIP LOCKED) "
                "UPDATE operational.lifecycle_mail_outbox o SET state='failed', "
                "encrypted_payload=NULL, claim_token=NULL, claimed_at=NULL, "
                "lease_until=NULL, sent_at=NULL, "
                "failure_code=CASE WHEN obsolete.expired THEN 'expired_proof' "
                "ELSE 'attempts_exhausted' END, "
                "updated_at=GREATEST(%s,clock_timestamp()) "
                "FROM obsolete WHERE o.id=obsolete.id",
                (now, now, now, max_attempts, now, now),
            )
        columns = ", ".join(f"o.{field}" for field in self._row_fields)
        row = self._one(
            "WITH candidate AS MATERIALIZED ("
            "SELECT o.id FROM operational.lifecycle_mail_outbox o "
            "JOIN operational.account_lifecycle_proofs p ON p.id=o.proof_id "
            "WHERE ((o.state='pending' AND o.next_attempt_at <= GREATEST(%s,clock_timestamp())) "
            "OR (o.state='claimed' AND o.lease_until <= GREATEST(%s,clock_timestamp()))) "
            "AND o.attempt_count < LEAST(%s,5) "
            "AND p.expires_at > GREATEST(%s,clock_timestamp()) "
            "ORDER BY o.next_attempt_at,o.id LIMIT 1 FOR UPDATE OF o SKIP LOCKED) "
            "UPDATE operational.lifecycle_mail_outbox o SET state='claimed', "
            "claim_token=%s, attempt_count=o.attempt_count+1, "
            "claimed_at=GREATEST(%s,clock_timestamp()), "
            "lease_until=GREATEST(%s,clock_timestamp()) + (%s * interval '1 second'), "
            "updated_at=GREATEST(%s,clock_timestamp()), failure_code=NULL "
            f"FROM candidate WHERE o.id=candidate.id RETURNING {columns}",
            (now, now, max_attempts, now, uuid4(), now, now, lease_seconds, now),
        )
        return self._claim(row) if row else None

    def owns_claim(self, claim: MailDeliveryClaim, now: datetime) -> bool:
        return (
            self._one(
                "SELECT id FROM operational.lifecycle_mail_outbox "
                "WHERE id=%s AND claim_token=%s AND state='claimed' "
                "AND lease_until > GREATEST(%s,clock_timestamp())",
                (claim.id, claim.claim_token, now),
            )
            is not None
        )

    def settle(
        self,
        claim: MailDeliveryClaim,
        now: datetime,
        *,
        state: Literal["pending", "sent", "failed", "suppressed"],
        failure_code: str | None = None,
        next_attempt_at: datetime | None = None,
    ) -> bool:
        if state not in ("pending", "sent", "failed", "suppressed"):
            raise ValueError("invalid lifecycle mail settlement state")
        if state == "pending" and next_attempt_at is None:
            raise ValueError("retry requires its next attempt time")
        # Acquire ownership before issuing the fresh-clock UPDATE. PostgreSQL
        # can evaluate an UPDATE filter before waiting even with a locking CTE.
        owned = self._one(
            "SELECT id FROM operational.lifecycle_mail_outbox "
            "WHERE id=%s AND claim_token=%s AND state='claimed' FOR UPDATE",
            (claim.id, claim.claim_token),
        )
        if owned is None:
            return False
        row = self._one(
            "UPDATE operational.lifecycle_mail_outbox o SET state=%s, "
            "encrypted_payload=CASE WHEN %s='pending' THEN o.encrypted_payload ELSE NULL END, "
            "claim_token=NULL, claimed_at=NULL, lease_until=NULL, "
            "sent_at=CASE WHEN %s='sent' THEN GREATEST(%s,clock_timestamp()) ELSE NULL END, "
            "failure_code=%s, next_attempt_at=COALESCE(%s,o.next_attempt_at), "
            "updated_at=GREATEST(%s,clock_timestamp()) "
            "WHERE o.id=%s AND o.claim_token=%s AND o.state='claimed' "
            "AND o.lease_until > GREATEST(%s,clock_timestamp()) "
            "AND (%s<>'pending' OR o.attempt_count<5) RETURNING o.id",
            (
                state,
                state,
                state,
                now,
                failure_code,
                next_attempt_at,
                now,
                claim.id,
                claim.claim_token,
                now,
                state,
            ),
        )
        return row is not None
