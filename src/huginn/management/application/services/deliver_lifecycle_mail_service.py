"""Durable bounded lifecycle mail delivery policy; lifecycle design section 4."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hmac import compare_digest
from typing import Literal

from huginn.management.application.constants.lifecycle_policy import (
    MAIL_CLAIM_LEASE_SECONDS,
    MAIL_MAX_ATTEMPTS,
)
from huginn.management.application.protocols.lifecycle_mail_outbox import (
    LifecycleMailOutboxRepository,
)
from huginn.management.application.protocols.lifecycle_mail_sender import (
    LifecycleMailSender,
)
from huginn.management.application.protocols.proof_cipher import ProofCipher
from huginn.management.application.read_models.mail_delivery_claim import (
    MailDeliveryClaim,
)
from huginn.management.application.requests.deliver_lifecycle_mail_request import (
    DeliverLifecycleMailRequest,
)
from huginn.management.application.responses.deliver_lifecycle_mail_response import (
    DeliverLifecycleMailResponse,
)
from huginn.management.domain.entities.account_lifecycle_proof import (
    AccountLifecycleProof,
)
from huginn.management.domain.value_objects.proof_purpose import ProofPurpose
from huginn.management.persistence.contracts.repositories.account import (
    AccountRepository,
)
from huginn.management.persistence.contracts.repositories.account_lifecycle_proof import (
    AccountLifecycleProofRepository,
)
from huginn.management.persistence.contracts.repositories.account_recovery_identity import (
    AccountRecoveryIdentityRepository,
)
from huginn.management.persistence.contracts.unit_of_work import UnitOfWorkProtocol
from huginn.management.security.lifecycle_proofs import digest_lifecycle_proof

logger = logging.getLogger(__name__)


class DeliverLifecycleMailService:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWorkProtocol],
        *,
        outbox_factory: Callable[[UnitOfWorkProtocol], LifecycleMailOutboxRepository],
        accounts_factory: Callable[[UnitOfWorkProtocol], AccountRepository],
        recovery_identities_factory: Callable[
            [UnitOfWorkProtocol], AccountRecoveryIdentityRepository
        ],
        proofs_factory: Callable[[UnitOfWorkProtocol], AccountLifecycleProofRepository],
        cipher: ProofCipher,
        sender: LifecycleMailSender,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._outbox_factory = outbox_factory
        self._accounts_factory = accounts_factory
        self._recovery_factory = recovery_identities_factory
        self._proofs_factory = proofs_factory
        self._cipher = cipher
        self._sender = sender
        self._clock = clock or (lambda: datetime.now(UTC))

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("lifecycle clock must be timezone-aware")
        return now.astimezone(UTC)

    def _snapshot(
        self, claim: MailDeliveryClaim
    ) -> tuple[AccountLifecycleProof | None, str | None]:
        with self._uow_factory() as uow:
            self._bound_queries(uow)
            # Identity writers use this same Account-first lock order.
            account = self._accounts_factory(uow).get_by_id_for_update(claim.account_id)
            proof = self._proofs_factory(uow).get_by_id(claim.proof_id)
            identity = self._recovery_factory(uow).get_by_account_id(claim.account_id)
            now = self._now()
            code = None
            if proof is not None and proof.expires_at <= now:
                code = "expired_proof"
            elif (
                account is None
                or account.status != "active"
                or proof is None
                or proof.id != claim.proof_id
                or proof.account_id != claim.account_id
                or proof.purpose.value != claim.purpose
                or proof.superseded
                or proof.consumed_at is not None
                or identity is None
                or identity.account_id != claim.account_id
                or proof.destination
                != (
                    identity.pending_email
                    if proof.purpose == ProofPurpose.VERIFY_EMAIL
                    else identity.verified_email
                )
            ):
                code = "obsolete_proof"
            uow.commit()
        return proof, code

    @staticmethod
    def _bound_queries(uow: UnitOfWorkProtocol) -> None:
        assert uow.connection is not None
        uow.connection.execute("SET LOCAL lock_timeout = '5s'")
        uow.connection.execute("SET LOCAL statement_timeout = '5s'")

    @staticmethod
    def _is_timeout(error: Exception) -> bool:
        return getattr(error, "sqlstate", None) in {"55P03", "57014"}

    @staticmethod
    def _lost_claim(claim: MailDeliveryClaim) -> DeliverLifecycleMailResponse:
        logger.info("Lifecycle mail outcome=lost_claim message_id=%s", claim.id)
        return DeliverLifecycleMailResponse(claim.id, "lost_claim")

    def _owns_claim(self, claim: MailDeliveryClaim) -> bool:
        now = self._now()
        if claim.lease_until <= now:
            return False
        with self._uow_factory() as uow:
            self._bound_queries(uow)
            owned = self._outbox_factory(uow).owns_claim(claim, now)
            uow.commit()
        return owned

    def _settle(
        self,
        claim: MailDeliveryClaim,
        *,
        state: Literal["pending", "sent", "failed", "suppressed"],
        outcome: Literal["sent", "retried", "suppressed", "failed"],
        failure_code: str | None = None,
        next_attempt_at: datetime | None = None,
    ) -> DeliverLifecycleMailResponse:
        try:
            with self._uow_factory() as uow:
                self._bound_queries(uow)
                settled = self._outbox_factory(uow).settle(
                    claim,
                    self._now(),
                    state=state,
                    failure_code=failure_code,
                    next_attempt_at=next_attempt_at,
                )
                uow.commit()
        except Exception as error:
            if self._is_timeout(error):
                return self._lost_claim(claim)
            raise
        response = DeliverLifecycleMailResponse(
            claim.id, outcome if settled else "lost_claim"
        )
        logger.info(
            "Lifecycle mail outcome=%s message_id=%s",
            response.outcome,
            response.message_id,
        )
        return response

    def execute(
        self, request: DeliverLifecycleMailRequest
    ) -> DeliverLifecycleMailResponse:
        with self._uow_factory() as uow:
            self._bound_queries(uow)
            claim = self._outbox_factory(uow).claim_due(
                self._now(),
                lease_seconds=MAIL_CLAIM_LEASE_SECONDS,
                max_attempts=MAIL_MAX_ATTEMPTS,
            )
            # The no-claim path can still have scrubbed expired/exhausted rows.
            uow.commit()
        if claim is None:
            logger.debug("Lifecycle mail outcome=idle")
            return DeliverLifecycleMailResponse(None, "idle")
        try:
            proof, code = self._snapshot(claim)
        except Exception as error:
            if self._is_timeout(error):
                return self._lost_claim(claim)
            raise
        if code is not None:
            return self._settle(
                claim, state="suppressed", outcome="suppressed", failure_code=code
            )
        assert proof is not None
        try:
            message = self._cipher.decrypt(claim.encrypted_payload)
            if (
                message.purpose != claim.purpose
                or message.recipient != proof.destination
                or not compare_digest(
                    digest_lifecycle_proof(message.token), proof.token_digest
                )
            ):
                raise ValueError("invalid lifecycle mail binding")
        except Exception:
            return self._settle(
                claim, state="failed", outcome="failed", failure_code="invalid_payload"
            )
        try:
            if not self._owns_claim(claim):
                return self._lost_claim(claim)
        except Exception as error:
            if self._is_timeout(error):
                return self._lost_claim(claim)
            raise
        try:
            self._sender.send(message)
        except Exception:
            # Deliberately omit exception text/traceback, including transport secrets.
            if claim.attempt_count >= MAIL_MAX_ATTEMPTS:
                return self._settle(
                    claim,
                    state="failed",
                    outcome="failed",
                    failure_code="attempts_exhausted",
                )
            retry_at = self._now() + timedelta(
                seconds=min(60 * 2 ** (claim.attempt_count - 1), 900)
            )
            return self._settle(
                claim,
                state="pending",
                outcome="retried",
                failure_code="transport_unavailable",
                next_attempt_at=retry_at,
            )
        return self._settle(claim, state="sent", outcome="sent")
