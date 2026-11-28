"""GetAccountSecurity use case; public-account-lifecycle design sections 1–4."""

from huginn.management.application.read_models.account_security import AccountSecurity
from huginn.management.application.requests.get_account_security_request import (
    GetAccountSecurityRequest,
)
from huginn.management.application.responses.get_account_security_response import (
    GetAccountSecurityResponse,
)
from huginn.management.application.services.signup_service import _LifecycleOperations


class GetAccountSecurityService(_LifecycleOperations):
    def execute(self, request: GetAccountSecurityRequest) -> GetAccountSecurityResponse:
        with self._uow_factory() as uow:
            account, user = self._owner(uow, request.principal)
            identity = self._identity(uow, account.id)
            return GetAccountSecurityResponse(
                AccountSecurity(
                    identity.verified_email or user.email,
                    identity.pending_email,
                    identity.verification_required,
                    identity.verified_email is not None,
                )
            )
