"""ForgotPassword use case; public-account-lifecycle design sections 1–4."""

from huginn.management.application.requests.forgot_password_request import (
    ForgotPasswordRequest,
)
from huginn.management.application.responses.forgot_password_response import (
    ForgotPasswordResponse,
)
from huginn.management.application.services.signup_service import _LifecycleOperations
from huginn.management.domain.services.identity_validation import normalized_email
from huginn.management.domain.value_objects.proof_purpose import ProofPurpose


class ForgotPasswordService(_LifecycleOperations):
    def execute(self, request: ForgotPasswordRequest) -> ForgotPasswordResponse:
        email = normalized_email(request.email)
        self._admit(request.client_ip, email=email)
        with self._uow_factory() as uow:
            located = self._recovery_factory(uow).get_by_email(email)
            if located is not None:
                account = self._accounts_factory(uow).get_by_id_for_update(
                    located.account_id
                )
                identity = self._identity(uow, located.account_id)
                destination = identity.verified_email
                if (
                    account is not None
                    and account.status == "active"
                    and destination is not None
                    and destination.strip().lower() == email
                ):
                    self._queue(uow, account, ProofPurpose.RESET_PASSWORD, destination)
            uow.commit()
        return ForgotPasswordResponse()
