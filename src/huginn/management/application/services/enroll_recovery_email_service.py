"""EnrollRecoveryEmail use case; public-account-lifecycle design sections 1–4."""

from huginn.management.application.constants.lifecycle_policy import (
    MAIL_COOLDOWN_SECONDS,
)
from huginn.management.application.errors.lifecycle import (
    LifecycleConflictError,
    LifecycleRateLimitError,
)
from huginn.management.application.requests.enroll_recovery_email_request import (
    EnrollRecoveryEmailRequest,
)
from huginn.management.application.responses.enroll_recovery_email_response import (
    EnrollRecoveryEmailResponse,
)
from huginn.management.application.services.signup_service import _LifecycleOperations
from huginn.management.domain.errors.errors import ConflictError, ValidationDomainError
from huginn.management.domain.services.identity_validation import normalized_email
from huginn.management.domain.value_objects.proof_purpose import ProofPurpose
from huginn.management.security.passwords import Password, verify_password


class EnrollRecoveryEmailService(_LifecycleOperations):
    def execute(
        self, request: EnrollRecoveryEmailRequest
    ) -> EnrollRecoveryEmailResponse:
        replacement = (
            normalized_email(request.email) if request.email is not None else None
        )
        if replacement is not None:
            self._admit(request.client_ip, email=replacement)
        with self._uow_factory() as uow:
            account, user = self._owner(uow, request.principal)
            identity = self._identity(uow, account.id)
            if replacement is not None:
                try:
                    current = Password(request.current_password)
                except (TypeError, ValueError) as exc:
                    raise ValidationDomainError(
                        "Current password is incorrect"
                    ) from exc
                if not verify_password(current, account.password_hash):
                    raise ValidationDomainError("Current password is incorrect")
                if replacement == identity.verified_email:
                    raise LifecycleConflictError("Enter a different email address")
            elif identity.verified_email is not None or identity.verification_required:
                raise LifecycleConflictError("Recovery email enrollment is unavailable")
            destination = replacement or normalized_email(user.email)
            if self._queue(uow, account, ProofPurpose.VERIFY_EMAIL, destination):
                try:
                    pending = self._recovery_factory(uow).set_pending_email(
                        account.id, destination
                    )
                except ConflictError as exc:
                    raise LifecycleConflictError(
                        "That email address cannot be used"
                    ) from exc
                if pending is None:
                    raise LifecycleConflictError("That email address cannot be used")
            elif replacement is not None:
                raise LifecycleRateLimitError(
                    "Wait before requesting another verification link",
                    MAIL_COOLDOWN_SECONDS,
                )
            uow.commit()
        return EnrollRecoveryEmailResponse()
