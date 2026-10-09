"""Trusted account role assignment use case."""

from collections.abc import Callable

from huginn.management.application.requests.assign_account_role_request import (
    AssignAccountRoleRequest,
)
from huginn.management.application.responses.assign_account_role_response import (
    AssignAccountRoleResponse,
)
from huginn.management.domain.errors.errors import NotFoundError
from huginn.management.persistence.contracts.repositories.account import (
    AccountRepository,
)
from huginn.management.persistence.contracts.unit_of_work import UnitOfWorkProtocol


class AssignAccountRoleService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWorkProtocol],
        *,
        accounts_factory: Callable[[UnitOfWorkProtocol], AccountRepository],
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._accounts_factory = accounts_factory

    def execute(self, request: AssignAccountRoleRequest) -> AssignAccountRoleResponse:
        with self._uow_factory() as uow:
            accounts = self._accounts_factory(uow)
            account = accounts.get_by_normalized_username(request.username)
            if account is None:
                raise NotFoundError("account not found")
            updated = accounts.set_role(account.id, request.role)
            if updated is None:
                raise NotFoundError("account not found")
            uow.commit()
            return AssignAccountRoleResponse(updated.id, updated.username, updated.role)
