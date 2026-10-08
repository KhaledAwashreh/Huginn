"""EnrollRecoveryEmail use case; public-account-lifecycle design sections 1–4."""

from datetime import timedelta

from huginn.management.application.constants.lifecycle_policy import (
    MAIL_COOLDOWN_SECONDS,
)
from huginn.management.application.errors.lifecycle import LifecycleConflictError
from huginn.management.application.requests.enroll_recovery_email_request import (
    EnrollRecoveryEmailRequest,
)
from huginn.management.application.responses.enroll_recovery_email_response import (
    EnrollRecoveryEmailResponse,
)
from huginn.management.application.services.signup_service import _LifecycleOperations
from huginn.management.domain.value_objects.proof_purpose import ProofPurpose


class EnrollRecoveryEmailService(_LifecycleOperations):
    def execute(
        self, request: EnrollRecoveryEmailRequest
    ) -> EnrollRecoveryEmailResponse:
        with self._uow_factory() as uow:
            account, user = self._owner(uow, request.principal)
            identity = self._identity(uow, account.id)
            if identity.verified_email is not None or identity.verification_required:
                raise LifecycleConflictError("Recovery email enrollment is unavailable")
            outbox = self._outbox_factory(uow)
            latest = outbox.last_enqueued_at(account.id, ProofPurpose.VERIFY_EMAIL)
            if latest is None or self._now() >= latest + timedelta(
                seconds=MAIL_COOLDOWN_SECONDS
            ):
                if (
                    self._recovery_factory(uow).set_pending_email(
                        account.id, user.email
                    )
                    is None
                ):
                    raise LifecycleConflictError(
                        "Recovery email enrollment is unavailable"
                    )
                self._queue(
                    uow, account, ProofPurpose.VERIFY_EMAIL, user.email, cooldown=False
                )
            uow.commit()
        return EnrollRecoveryEmailResponse()
