"""VerifyEmail use case; public-account-lifecycle design sections 1–4."""

from huginn.management.application.errors.lifecycle import LifecycleIntegrityError
from huginn.management.application.requests.verify_email_request import (
    VerifyEmailRequest,
)
from huginn.management.application.responses.verify_email_response import (
    VerifyEmailResponse,
)
from huginn.management.application.services.signup_service import _LifecycleOperations
from huginn.management.domain.errors.errors import ConflictError
from huginn.management.domain.errors.lifecycle import LifecycleProofError
from huginn.management.domain.value_objects.proof_purpose import ProofPurpose
from huginn.management.domain.value_objects.user import UserChanges


class VerifyEmailService(_LifecycleOperations):
    def execute(self, request: VerifyEmailRequest) -> VerifyEmailResponse:
        self._admit(request.client_ip)
        with self._uow_factory() as uow:
            account, proof = self._proof(uow, request.token, ProofPurpose.VERIFY_EMAIL)
            now = self._now()
            proofs = self._proofs_factory(uow)
            if not proofs.consume(proof.id, now):
                raise LifecycleProofError("This link is invalid or expired")
            identity = self._recovery_factory(uow).verify_email(
                account.id, proof.destination, now
            )
            if identity is None or identity.verified_email is None:
                raise LifecycleProofError("This link is invalid or expired")
            users = self._users_factory(uow)
            user = users.get_by_account_id(account.id)
            if user is not None and user.email != identity.verified_email:
                try:
                    updated = users.update(
                        user.id,
                        UserChanges(
                            {"email": identity.verified_email}, frozenset({"email"})
                        ),
                    )
                except ConflictError as exc:
                    raise LifecycleProofError(
                        "This link is invalid or expired"
                    ) from exc
                if updated is None:
                    raise LifecycleIntegrityError(
                        "Account security data is unavailable"
                    )
            proofs.supersede_for_account(account.id, ProofPurpose.RESET_PASSWORD)
            uow.commit()
        return VerifyEmailResponse()
