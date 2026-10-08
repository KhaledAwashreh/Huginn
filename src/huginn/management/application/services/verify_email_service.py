"""VerifyEmail use case; public-account-lifecycle design sections 1–4."""

from huginn.management.application.requests.verify_email_request import (
    VerifyEmailRequest,
)
from huginn.management.application.responses.verify_email_response import (
    VerifyEmailResponse,
)
from huginn.management.application.services.signup_service import _LifecycleOperations
from huginn.management.domain.errors.lifecycle import LifecycleProofError
from huginn.management.domain.value_objects.proof_purpose import ProofPurpose


class VerifyEmailService(_LifecycleOperations):
    def execute(self, request: VerifyEmailRequest) -> VerifyEmailResponse:
        self._admit(request.client_ip)
        with self._uow_factory() as uow:
            account, proof = self._proof(uow, request.token, ProofPurpose.VERIFY_EMAIL)
            now = self._now()
            if not self._proofs_factory(uow).consume(proof.id, now):
                raise LifecycleProofError("This link is invalid or expired")
            if (
                self._recovery_factory(uow).verify_email(
                    account.id, proof.destination, now
                )
                is None
            ):
                raise LifecycleProofError("This link is invalid or expired")
            uow.commit()
        return VerifyEmailResponse()
