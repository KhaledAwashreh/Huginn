from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from huginn.management.domain.entities.account import Account
from huginn.management.domain.value_objects.account_role import AccountRole
from huginn.management.domain.value_objects.common import Principal


def test_account_roles_are_frozen_and_reject_unknown_roles():
    role = AccountRole("admin")
    with pytest.raises(FrozenInstanceError):
        role.value = "user"
    with pytest.raises(ValueError):
        AccountRole("owner")


def test_account_and_principal_default_to_user_role():
    now = datetime.now(UTC)
    account = Account(uuid4(), "alice", "hash", "active", now, now)
    principal = Principal(uuid4(), uuid4())
    assert account.role == AccountRole("user")
    assert principal.role == AccountRole("user")


def test_administrator_dependency_checks_the_role_from_authenticated_principal():
    from datetime import UTC, datetime, timedelta

    from huginn.management.application.errors.errors import AuthorizationError
    from huginn.management.domain.entities.session import Session
    from huginn.management.presentation.api.dependencies.administrator import (
        require_administrator,
    )
    from huginn.management.presentation.api.dependencies.authentication import (
        AuthenticatedSession,
    )

    now = datetime.now(UTC)
    session = Session(
        uuid4(), uuid4(), "token", "csrf", now, now + timedelta(hours=1), None
    )
    user = AuthenticatedSession(Principal(uuid4(), uuid4()), session, "token")
    with pytest.raises(AuthorizationError):
        require_administrator(user)
    admin = AuthenticatedSession(
        Principal(
            user.principal.account_id, user.principal.user_id, AccountRole("admin")
        ),
        session,
        "token",
    )
    assert require_administrator(admin) is admin


def test_role_assignment_updates_only_the_role_and_commits():
    from dataclasses import replace
    from datetime import UTC, datetime

    from huginn.management.application.requests.assign_account_role_request import (
        AssignAccountRoleRequest,
    )
    from huginn.management.application.services.assign_account_role_service import (
        AssignAccountRoleService,
    )
    from tests.management.test_app_authentication import FakeUnitOfWork

    now = datetime.now(UTC)
    account = Account(uuid4(), "Alice", "hash", "disabled", now, now)

    class Accounts:
        def __init__(self):
            self.updated = None

        def get_by_normalized_username(self, username):
            assert username == " Alice "
            return account

        def set_role(self, account_id, role):
            assert account_id == account.id
            self.updated = role
            return replace(account, role=role)

    uow, accounts = FakeUnitOfWork(), Accounts()
    service = AssignAccountRoleService(lambda: uow, accounts_factory=lambda _: accounts)
    result = service.execute(AssignAccountRoleRequest(" Alice ", AccountRole("admin")))
    assert result.role == AccountRole("admin")
    assert accounts.updated == AccountRole("admin")
    assert account.status == "disabled"
    assert uow.commits == 1
