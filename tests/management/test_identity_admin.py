from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from huginn.management.application.commands.provisioning import ProvisionIdentity
from huginn.management.application.services.provisioning import (
    IdentityProvisioningService,
)
from huginn.management.application.services.provisioning import (
    IdentityProvisioningService as DomainIdentityProvisioningService,
)
from huginn.management.domain.entities.account import Account
from huginn.management.domain.entities.professional_profile import ProfessionalProfile
from huginn.management.domain.entities.user import User
from huginn.management.persistence.repositories.account import PostgresAccountRepository


def test_username_lookup_trims_but_uses_postgres_lower_for_case_insensitivity():
    class Cursor:
        def __init__(self, row):
            self.row = row

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, query, params):
            self.query, self.params = query, params

        def fetchone(self):
            return self.row

    class Connection:
        def __init__(self, row):
            self.row = row
            self.last = None

        def cursor(self):
            self.last = Cursor(self.row)
            return self.last

    now, account_id = datetime.now(UTC), uuid4()
    connection = Connection(
        (account_id, "Alice", "scrypt$hash", "active", now, now, "admin")
    )
    result = PostgresAccountRepository(connection).get_by_normalized_username(" Alice ")
    assert result.id == account_id
    assert result.role.value == "admin"
    assert "lower(username) = lower(%s)" in connection.last.query
    assert connection.last.params == ("Alice",)


def test_role_lookup_uses_authoritative_account_role_on_every_live_session_read():
    from datetime import UTC, datetime
    from uuid import uuid4

    from huginn.management.persistence.repositories.session import (
        PostgresSessionRepository,
    )

    class Cursor:
        def __init__(self, connection):
            self.connection = connection

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, query, params):
            self.connection.queries.append((query, params))

        def fetchone(self):
            return self.connection.row

    class Connection:
        def __init__(self, row):
            self.row = row
            self.queries = []

        def cursor(self):
            return Cursor(self)

    now = datetime.now(UTC)
    connection = Connection((uuid4(), uuid4(), "admin"))
    repository = PostgresSessionRepository(connection)
    assert (
        repository.get_active_principal_by_token_digest("digest", now).role.value
        == "admin"
    )
    connection.row = (connection.row[0], connection.row[1], "user")
    assert (
        repository.get_active_principal_by_token_digest("digest", now).role.value
        == "user"
    )
    assert len(connection.queries) == 2
    assert all("a.role" in query for query, _ in connection.queries)


class FakeUow:
    def __init__(self, connection=None):
        self.connection = connection
        self.commits = self.rollbacks = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        if not self.commits and not self.rollbacks:
            self.rollback()
        return False

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class FakeRepository:
    def __init__(self, kind, *, fail=False):
        self.kind, self.fail, self.created = kind, fail, []

    def get_by_normalized_username(self, _):
        return None

    def create(self, value):
        self.created.append(value)
        if self.fail:
            raise RuntimeError("injected persistence failure")
        now, ident = datetime.now(UTC), uuid4()
        if self.kind == "account":
            return Account(
                ident, value.username, value.password_hash, value.status, now, now
            )
        if self.kind == "user":
            return User(
                ident,
                value.account_id,
                value.first_name,
                value.last_name,
                value.email,
                value.phone_number,
                value.country_of_residence,
                value.timezone,
                now,
                now,
            )
        return ProfessionalProfile(
            ident, value.user_id, None, None, (), (), (), now, now
        )


class FakeRecoveryIdentityRepository:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.created = []

    def create(self, account_id, *, verification_required, pending_email=None):
        self.created.append((account_id, verification_required, pending_email))
        if self.fail:
            raise RuntimeError("injected recovery identity failure")
        return object()


def _provision(
    service,
    *,
    username="Alice",
    password="a long owner password",
    phone_number="+12025550123",
):
    return service.provision(
        ProvisionIdentity(
            username,
            "Ada",
            "Lovelace",
            "ada@example.test",
            phone_number,
            "US",
            "UTC",
            password,
        )
    )


@pytest.mark.parametrize("failure", ["account", "user", "profile"])
def test_provisioning_injected_failure_rolls_back_each_stage(failure):
    uow = FakeUow()
    repos = [
        FakeRepository("account", fail=failure == "account"),
        FakeRepository("user", fail=failure == "user"),
        FakeRepository("profile", fail=failure == "profile"),
    ]
    service = IdentityProvisioningService(
        lambda: uow,
        accounts_factory=lambda _: repos[0],
        users_factory=lambda _: repos[1],
        profiles_factory=lambda _: repos[2],
        recovery_identities_factory=lambda _: FakeRecoveryIdentityRepository(),
        hash_password_fn=lambda _: "scrypt$hash",
    )
    with pytest.raises(RuntimeError, match="injected"):
        _provision(service)
    assert (uow.commits, uow.rollbacks) == (0, 1)
    stage = ["account", "user", "profile"].index(failure)
    assert [len(repo.created) for repo in repos] == [int(i <= stage) for i in range(3)]


def test_provisioning_recovery_identity_failure_rolls_back_every_identity_write():
    uow = FakeUow()
    repos = [FakeRepository(kind) for kind in ("account", "user", "profile")]
    recovery = FakeRecoveryIdentityRepository(fail=True)
    service = IdentityProvisioningService(
        lambda: uow,
        accounts_factory=lambda _: repos[0],
        users_factory=lambda _: repos[1],
        profiles_factory=lambda _: repos[2],
        recovery_identities_factory=lambda _: recovery,
        hash_password_fn=lambda _: "scrypt$hash",
    )

    with pytest.raises(RuntimeError, match="recovery identity"):
        _provision(service)

    assert (uow.commits, uow.rollbacks) == (0, 1)
    assert [len(repo.created) for repo in repos] == [1, 1, 1]
    assert len(recovery.created) == 1
    assert isinstance(recovery.created[0][0], UUID)
    assert recovery.created[0][1:] == (False, None)


def test_provisioning_returns_all_ids_and_preserves_username_spelling():
    uow = FakeUow()
    repos = [FakeRepository(kind) for kind in ("account", "user", "profile")]
    recovery = FakeRecoveryIdentityRepository()
    service = IdentityProvisioningService(
        lambda: uow,
        accounts_factory=lambda _: repos[0],
        users_factory=lambda _: repos[1],
        profiles_factory=lambda _: repos[2],
        recovery_identities_factory=lambda _: recovery,
        hash_password_fn=lambda _: "scrypt$hash",
    )
    result = _provision(service, username="Alice")
    assert result.username == "Alice"
    assert all(
        isinstance(value, UUID)
        for value in (result.account_id, result.user_id, result.profile_id)
    )
    assert not hasattr(result, "password_hash")
    assert (uow.commits, uow.rollbacks) == (1, 0)
    assert recovery.created == [(result.account_id, False, None)]


def test_domain_provisioning_service_accepts_command_value():
    uow = FakeUow()
    repos = [FakeRepository(kind) for kind in ("account", "user", "profile")]
    service = DomainIdentityProvisioningService(
        lambda: uow,
        accounts_factory=lambda _: repos[0],
        users_factory=lambda _: repos[1],
        profiles_factory=lambda _: repos[2],
        recovery_identities_factory=lambda _: FakeRecoveryIdentityRepository(),
        hash_password_fn=lambda _: "scrypt$hash",
    )
    result = service.provision(
        ProvisionIdentity(
            "Alice",
            "Ada",
            "Lovelace",
            "ada@example.test",
            "+12025550123",
            "US",
            "UTC",
            "a long owner password",
        )
    )

    assert result.username == "Alice"
    assert (uow.commits, uow.rollbacks) == (1, 0)


def test_invalid_password_names_password_without_echoing_value():
    from huginn.management.domain.errors.errors import ValidationDomainError

    with pytest.raises(ValidationDomainError, match="password") as error:
        _provision(
            IdentityProvisioningService(
                lambda: FakeUow(),
                accounts_factory=lambda _: FakeRepository("account"),
                users_factory=lambda _: FakeRepository("user"),
                profiles_factory=lambda _: FakeRepository("profile"),
                recovery_identities_factory=lambda _: FakeRecoveryIdentityRepository(),
            ),
            password="short",
        )
    assert "short" not in str(error.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("username", "   "),
        ("first_name", "   "),
        ("last_name", "   "),
        ("email", "invalid-email"),
        ("phone_number", "2025550123"),
        ("country_of_residence", "  "),
        ("timezone", "Mars/Olympus"),
    ],
)
def test_provisioning_rejects_invalid_identity_fields_before_opening_uow(field, value):
    from dataclasses import replace

    from huginn.management.domain.errors.errors import ValidationDomainError

    opened = []
    service = IdentityProvisioningService(
        lambda: (opened.append(True), FakeUow())[1],
        accounts_factory=lambda _: FakeRepository("account"),
        users_factory=lambda _: FakeRepository("user"),
        profiles_factory=lambda _: FakeRepository("profile"),
        recovery_identities_factory=lambda _: FakeRecoveryIdentityRepository(),
    )
    identity = ProvisionIdentity(
        "Alice",
        "Ada",
        "Lovelace",
        "ada@example.test",
        "+12025550123",
        "US",
        "UTC",
        "a long owner password",
    )
    with pytest.raises(ValidationDomainError, match=field) as error:
        service.provision(replace(identity, **{field: value}))
    assert opened == []
    assert value not in str(error.value)


def test_provisioning_normalizes_identity_fields_before_persistence():
    uow = FakeUow()
    repos = [FakeRepository(kind) for kind in ("account", "user", "profile")]
    service = IdentityProvisioningService(
        lambda: uow,
        accounts_factory=lambda _: repos[0],
        users_factory=lambda _: repos[1],
        profiles_factory=lambda _: repos[2],
        recovery_identities_factory=lambda _: FakeRecoveryIdentityRepository(),
        hash_password_fn=lambda _: "scrypt$hash",
    )
    service.provision(
        ProvisionIdentity(
            " Alice ",
            " Ada ",
            " Lovelace ",
            " ada@example.test ",
            "+12025550123",
            " US ",
            "UTC",
            "a long owner password",
        )
    )
    assert repos[0].created[0].username == "Alice"
    user = repos[1].created[0]
    assert (user.first_name, user.last_name, user.email) == (
        "Ada",
        "Lovelace",
        "ada@example.test",
    )
    assert user.country_of_residence == "US"


def test_cli_reads_matching_stdin_password_twice_and_rejects_argv_password(
    monkeypatch, capsys
):
    from io import StringIO

    from huginn.management.presentation.cli.account_admin import _password, main

    monkeypatch.setattr("sys.stdin", StringIO("secret password\nsecret password\n"))
    assert _password(stdin=True) == "secret password"
    monkeypatch.setattr("sys.stdin", StringIO("one password\ntwo password\n"))
    with pytest.raises(ValueError, match="do not match"):
        _password(stdin=True)
    sentinel = "never-print-this-secret"
    assert main(["account", "provision", "--password", sentinel]) == 2
    assert sentinel not in capsys.readouterr().err


def test_cli_requires_explicit_confirmation_for_role_assignment(capsys):
    from types import SimpleNamespace

    from huginn.management.presentation.cli.account_admin import main

    class RoleService:
        def __init__(self):
            self.requests = []

        def execute(self, request):
            self.requests.append(request)
            return SimpleNamespace(username=request.username, role=request.role)

    service = RoleService()

    def factory():
        return SimpleNamespace(role_assignment=service)

    args = ["account", "assign-role", "--username", "Alice", "--role", "admin"]
    assert main(args, services_factory=factory) == 2
    assert service.requests == []
    assert "--confirm" in capsys.readouterr().err
    assert main([*args, "--confirm"], services_factory=factory) == 0
    assert service.requests[0].role.value == "admin"
    assert "Assigned admin role to account Alice" in capsys.readouterr().out


def test_cli_prompt_and_username_conflict_are_safe(monkeypatch, capsys):
    from types import SimpleNamespace

    from huginn.management.domain.errors.errors import ConflictError
    from huginn.management.presentation.cli import account_admin as admin

    prompts = iter(("some password", "some password"))
    calls = []
    monkeypatch.setattr(
        admin.getpass,
        "getpass",
        lambda prompt: calls.append(prompt) or next(prompts),
    )
    assert admin._password(stdin=False) == "some password"
    assert calls == ["Password: ", "Confirm password: "]

    class ConflictService:
        def __init__(self, *_, **__):
            pass

        def set_status(self, *_):
            raise ConflictError("username is already in use")

    assert (
        admin.main(
            ["account", "disable", "--username", "Alice"],
            services_factory=lambda: SimpleNamespace(lifecycle=ConflictService()),
        )
        == 2
    )
    output = capsys.readouterr().err
    assert "username already in use" in output
    assert "hash" not in output and "some password" not in output


def test_cli_field_validation_output_is_specific_and_redacted(monkeypatch, capsys):
    from types import SimpleNamespace

    from huginn.management.domain.errors.errors import ValidationDomainError
    from huginn.management.presentation.cli import account_admin as admin

    class InvalidService:
        def __init__(self, *_, **__):
            pass

        def provision(self, _):
            raise ValidationDomainError("invalid identity fields: phone_number")

    monkeypatch.setattr(admin, "_password", lambda **_: "do-not-print-password")
    assert (
        admin.main(
            [
                "account",
                "provision",
                "--username",
                "Alice",
                "--first-name",
                "Ada",
                "--last-name",
                "Lovelace",
                "--email",
                "ada@example.test",
                "--phone-number",
                "+12025550123",
                "--country-of-residence",
                "US",
            ],
            services_factory=lambda: SimpleNamespace(provisioning=InvalidService()),
        )
        == 2
    )
    output = capsys.readouterr().err
    assert "phone_number" in output
    assert "do-not-print-password" not in output


def test_cli_preserves_safe_database_failure_class_name(capsys):
    from types import SimpleNamespace

    import psycopg

    from huginn.management.application.services.account_admin import AccountAdminService
    from huginn.management.persistence.database.client import (
        ManagementConnectionFactory,
    )
    from huginn.management.persistence.database.unit_of_work import UnitOfWork
    from huginn.management.presentation.cli.account_admin import main

    def failing_connector(*args, **kwargs):
        raise psycopg.OperationalError("database password-sentinel")

    factory = ManagementConnectionFactory("dsn", connector=failing_connector)
    service = AccountAdminService(
        lambda: UnitOfWork(factory),
        accounts_factory=lambda _: None,
        sessions_factory=lambda _: None,
    )
    assert (
        main(
            ["account", "disable", "--username", "owner"],
            services_factory=lambda: SimpleNamespace(lifecycle=service),
        )
        == 2
    )
    assert capsys.readouterr().err == "Account command failed: OperationalError\n"
