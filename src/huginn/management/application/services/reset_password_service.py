"""ResetPassword use case; public-account-lifecycle design sections 1–4."""

from huginn.management.application.errors.lifecycle import LifecycleIntegrityError
from huginn.management.application.requests.reset_password_request import (
    ResetPasswordRequest,
)
from huginn.management.application.responses.reset_password_response import (
    ResetPasswordResponse,
)
from huginn.management.application.services.signup_service import _LifecycleOperations
from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.errors.lifecycle import LifecycleProofError
from huginn.management.domain.value_objects.proof_purpose import ProofPurpose
from huginn.management.security.passwords import validate_new_password


class ResetPasswordService(_LifecycleOperations):
    def execute(self, request: ResetPasswordRequest) -> ResetPasswordResponse:
        try:
            password = validate_new_password(request.new_password)
        except (TypeError, ValueError) as exc:
            raise ValidationDomainError("invalid password") from exc
        self._admit(request.client_ip)
        encoded = self._hash_password(password)
        with self._uow_factory() as uow:
            account, proof = self._proof(
                uow, request.token, ProofPurpose.RESET_PASSWORD
            )
            now = self._now()
            proofs = self._proofs_factory(uow)
            if not proofs.consume(proof.id, now):
                raise LifecycleProofError("This link is invalid or expired")
            if (
                self._accounts_factory(uow).set_password_hash(account.id, encoded)
                is None
            ):
                raise LifecycleIntegrityError("Account security data is unavailable")
            if self._sessions_factory is None:
                raise LifecycleIntegrityError("Account security data is unavailable")
            self._sessions_factory(uow).revoke_for_account(account.id, now)
            proofs.supersede_for_account(account.id, ProofPurpose.RESET_PASSWORD)
            if self._recovery_factory(uow).cancel_pending_replacement(account.id):
                proofs.supersede_for_account(account.id, ProofPurpose.VERIFY_EMAIL)
            uow.commit()
        return ResetPasswordResponse()
