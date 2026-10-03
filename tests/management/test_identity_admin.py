from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from huginn.management.domain.account import Account
from huginn.management.domain.professional_profile import ProfessionalProfile
from huginn.management.domain.provisioning import ProvisionIdentity
from huginn.management.domain.user import User
from huginn.management.repositories.postgres.account import PostgresAccountRepository
from huginn.management.services.provisioning import IdentityProvisioningService
from huginn.management.services.provisioning import (
    IdentityProvisioningService as DomainIdentityProvisioningService,
)


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
    connection = Connection((account_id, "Alice", "scrypt$hash", "active", now, now))
    result = PostgresAccountRepository(connection).get_by_normalized_username(" Alice ")
    assert result.id == account_id
    assert "lower(username) = lower(%s)" in connection.last.query
    assert connection.last.params == ("Alice",)


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
        hash_password_fn=lambda _: "scrypt$hash",
    )
    with pytest.raises(RuntimeError, match="injected"):
        _provision(service)
    assert (uow.commits, uow.rollbacks) == (0, 1)
    stage = ["account", "user", "profile"].index(failure)
    assert [len(repo.created) for repo in repos] == [int(i <= stage) for i in range(3)]


def test_provisioning_returns_all_ids_and_preserves_username_spelling():
    uow = FakeUow()
    repos = [FakeRepository(kind) for kind in ("account", "user", "profile")]
    service = IdentityProvisioningService(
        lambda: uow,
        accounts_factory=lambda _: repos[0],
        users_factory=lambda _: repos[1],
        profiles_factory=lambda _: repos[2],
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


def test_domain_provisioning_service_accepts_command_value():
    uow = FakeUow()
    repos = [FakeRepository(kind) for kind in ("account", "user", "profile")]
    service = DomainIdentityProvisioningService(
        lambda: uow,
        accounts_factory=lambda _: repos[0],
        users_factory=lambda _: repos[1],
        profiles_factory=lambda _: repos[2],
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
    from huginn.management.errors.domain import ValidationDomainError

    with pytest.raises(ValidationDomainError, match="password") as error:
        _provision(
            IdentityProvisioningService(
                lambda: FakeUow(),
                accounts_factory=lambda _: FakeRepository("account"),
                users_factory=lambda _: FakeRepository("user"),
                profiles_factory=lambda _: FakeRepository("profile"),
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

    from huginn.management.errors.domain import ValidationDomainError

    opened = []
    service = IdentityProvisioningService(
        lambda: (opened.append(True), FakeUow())[1],
        accounts_factory=lambda _: FakeRepository("account"),
        users_factory=lambda _: FakeRepository("user"),
        profiles_factory=lambda _: FakeRepository("profile"),
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

    from huginn.management.admin import _password, main

    monkeypatch.setattr("sys.stdin", StringIO("secret password\nsecret password\n"))
    assert _password(stdin=True) == "secret password"
    monkeypatch.setattr("sys.stdin", StringIO("one password\ntwo password\n"))
    with pytest.raises(ValueError, match="do not match"):
        _password(stdin=True)
    sentinel = "never-print-this-secret"
    assert main(["account", "provision", "--password", sentinel]) == 2
    assert sentinel not in capsys.readouterr().err


def test_cli_prompt_and_username_conflict_are_safe(monkeypatch, capsys):
    from types import SimpleNamespace

    from huginn.management import admin
    from huginn.management.errors.domain import ConflictError

    prompts = iter(("some password", "some password"))
    calls = []
    monkeypatch.setattr(
        admin.getpass,
        "getpass",
        lambda prompt: calls.append(prompt) or next(prompts),
    )
    assert admin._password(stdin=False) == "some password"
    assert calls == ["Password: ", "Confirm password: "]
    monkeypatch.setattr(
        admin, "load_config", lambda: SimpleNamespace(database_url="dsn")
    )
    monkeypatch.setattr(admin, "ManagementConnectionFactory", lambda _: object())

    class ConflictService:
        def __init__(self, *_, **__):
            pass

        def set_status(self, *_):
            raise ConflictError("username is already in use")

    monkeypatch.setattr(admin, "AccountAdminService", ConflictService)
    assert admin.main(["account", "disable", "--username", "Alice"]) == 2
    output = capsys.readouterr().err
    assert "username already in use" in output
    assert "hash" not in output and "some password" not in output


def test_cli_field_validation_output_is_specific_and_redacted(monkeypatch, capsys):
    from types import SimpleNamespace

    from huginn.management import admin
    from huginn.management.errors.domain import ValidationDomainError

    monkeypatch.setattr(
        admin, "load_config", lambda: SimpleNamespace(database_url="dsn")
    )
    monkeypatch.setattr(admin, "ManagementConnectionFactory", lambda _: object())

    class InvalidService:
        def __init__(self, *_, **__):
            pass

        def provision(self, _):
            raise ValidationDomainError("invalid identity fields: phone_number")

    monkeypatch.setattr(admin, "IdentityProvisioningService", InvalidService)
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
            ]
        )
        == 2
    )
    output = capsys.readouterr().err
    assert "phone_number" in output
    assert "do-not-print-password" not in output
