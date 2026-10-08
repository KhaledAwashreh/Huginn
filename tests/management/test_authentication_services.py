from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from huginn.management.application.errors.errors import (
    AuthenticationError,
    RateLimitError,
)
from huginn.management.application.services.authentication import AuthenticationService
from huginn.management.config import ManagementConfig
from huginn.management.domain.entities.account import Account
from huginn.management.security.csrf import derive_csrf_token

NOW = datetime(2026, 1, 2, tzinfo=UTC)
PASSWORD = "correct horse battery staple"
GENERIC_FAILURE = "invalid username or password"


class Uow:
    def __init__(self, fail_commit=False):
        self.commits = self.rollbacks = 0
        self.fail_commit = fail_commit

    def __enter__(self):
        return self

    def __exit__(self, *_):
        if not self.commits:
            self.rollback()

    def commit(self):
        self.commits += 1
        if self.fail_commit:
            self.rollbacks += 1
            raise RuntimeError("commit failure")

    def rollback(self):
        self.rollbacks += 1


class Accounts:
    def __init__(self, account=None, fail_set=False):
        self.account, self.fail_set = account, fail_set
        self.set_hashes, self.lookups, self.locked_lookups = [], [], []
        self.id_locked_lookups = []

    def get_by_normalized_username(self, username):
        self.lookups.append(username)
        return self.account

    def get_by_normalized_username_for_update(self, username):
        self.locked_lookups.append(username)
        return self.account

    def get_by_id(self, account_id):
        return self.account if self.account and self.account.id == account_id else None

    def get_by_id_for_update(self, account_id):
        self.id_locked_lookups.append(account_id)
        return self.get_by_id(account_id)

    def set_password_hash(self, account_id, value):
        if self.fail_set:
            raise RuntimeError("password write failure")
        self.set_hashes.append((account_id, value))
        self.account = replace(self.account, password_hash=value)
        return self.account


class Sessions:
    def __init__(self, fail_create=False, fail_revoke=False):
        self.created, self.revoked = [], []
        self.fail_create, self.fail_revoke = fail_create, fail_revoke

    def create(self, value):
        if self.fail_create:
            raise RuntimeError("session write failure")
        self.created.append(value)

    def revoke_for_account(self, account_id, at):
        if self.fail_revoke:
            raise RuntimeError("session revoke failure")
        self.revoked.append((account_id, at))


class Throttle:
    def __init__(self, limited=False):
        self.limited = limited
        self.checks, self.failures, self.successes = [], [], []

    def check(self, ip, username):
        self.checks.append((ip, username))
        if self.limited:
            raise RateLimitError("login attempts are temporarily limited")

    def reserve(self, ip, username):
        self.checks.append((ip, username))
        if self.limited:
            raise RateLimitError("login attempts are temporarily limited")
        return (ip, username, len(self.checks))

    def record_failure(self, ip, username, reservation=None):
        self.failures.append((ip, username))

    def record_success(self, ip, username, reservation=None):
        self.successes.append((ip, username))

    def release(self, reservation):
        pass


def owner(status="active", password_hash="stored-hash"):
    return Account(uuid4(), "Owner", password_hash, status, NOW, NOW)


def make_login(
    *,
    account=None,
    valid=True,
    throttle=None,
    sessions=None,
    rehash=False,
    password_method="scrypt",
    verify=None,
    hash_fn=None,
    uow=None,
    dummy_hash="dummy-hash",
    use_werkzeug_rehash=False,
    recovery_identity=...,
):
    uow, repos = uow or Uow(), Accounts(account)
    sessions, throttle = sessions or Sessions(), throttle or Throttle()
    if recovery_identity is ...:
        recovery_identity = SimpleNamespace(
            verification_required=False, verified_email=None
        )
    verified = []

    def verifier(password, encoded):
        verified.append((password.value, encoded))
        return valid

    service = AuthenticationService(
        lambda: uow,
        ManagementConfig("postgresql://ignored", session_ttl=timedelta(hours=2)),
        throttle,
        accounts_factory=lambda _: repos,
        recovery_identities_factory=lambda _: SimpleNamespace(
            get_by_account_id=lambda _: recovery_identity
        ),
        sessions_factory=lambda _: sessions,
        clock=lambda: NOW,
        token_generator=iter(("session-secret", "csrf-secret")).__next__,
        verify_password_fn=verify or verifier,
        hash_password_fn=hash_fn or (lambda _: "new-hash"),
        needs_rehash_fn=(None if use_werkzeug_rehash else lambda _: rehash),
        password_method=password_method,
        dummy_password_hash=(None if use_werkzeug_rehash else dummy_hash),
    )
    return service, uow, repos, sessions, throttle, verified


@pytest.mark.parametrize(
    "account_value,valid",
    [
        (None, False),
        (owner(), False),
        (owner("disabled"), True),
    ],
)
def test_login_credential_failures_are_generic_and_counted(account_value, valid):
    service, uow, _, sessions, throttle, checked = make_login(
        account=account_value, valid=valid
    )
    with pytest.raises(AuthenticationError) as raised:
        service.login(username="Owner", password=PASSWORD, client_ip="192.0.2.1")
    assert str(raised.value) == GENERIC_FAILURE
    assert len(checked) == 1
    if account_value is None or account_value.status == "disabled":
        assert checked == [(PASSWORD, "dummy-hash")]
    assert throttle.failures == [("192.0.2.1", "Owner")]
    assert throttle.successes == [] and sessions.created == []
    assert uow.rollbacks == 1 and uow.commits == 0


def test_login_checks_throttle_before_password_validation_and_counts_invalid_length():
    service, _, _, sessions, throttle, checked = make_login()
    with pytest.raises(AuthenticationError) as raised:
        service.login(username="Owner", password="short", client_ip="192.0.2.1")
    assert str(raised.value) == GENERIC_FAILURE
    assert throttle.checks == [("192.0.2.1", "Owner")]
    assert throttle.failures == [("192.0.2.1", "Owner")]
    assert sessions.created == [] and checked == []


def test_limited_login_stops_before_lookup():
    service, uow, repos, _, throttle, _ = make_login(
        account=owner(), throttle=Throttle(limited=True)
    )
    with pytest.raises(RateLimitError):
        service.login(username="Owner", password=PASSWORD, client_ip="192.0.2.1")
    assert repos.lookups == [] and uow.rollbacks == 0
    assert throttle.failures == []


def test_login_success_persists_digest_session_commits_then_resets_throttle():
    account_value = owner()
    service, uow, repos, sessions, throttle, checked = make_login(account=account_value)
    result = service.login(username="Owner", password=PASSWORD, client_ip="192.0.2.1")
    assert result.account_id == account_value.id
    assert (
        result.session_token == "session-secret"
        and result.csrf_token == derive_csrf_token("session-secret")
    )
    assert "session-secret" not in repr(result) and "csrf-secret" not in repr(result)
    assert len(sessions.created) == 1
    assert sessions.created[0].token_digest != result.session_token
    assert sessions.created[0].csrf_digest != result.csrf_token
    assert checked == [(PASSWORD, "stored-hash")]
    assert repos.locked_lookups == ["Owner"]
    assert uow.commits == 1 and uow.rollbacks == 0
    assert throttle.successes == [("192.0.2.1", "Owner")]


def test_login_rehashes_when_full_scrypt_parameters_change_and_keeps_current_default():
    from werkzeug.security import generate_password_hash

    old = owner(password_hash="scrypt:16384:8:1$salt$hash")
    service, _, repos, _, _, _ = make_login(
        account=old, use_werkzeug_rehash=True, hash_fn=lambda _: "upgraded"
    )
    service.login(username="Owner", password=PASSWORD, client_ip="192.0.2.1")
    assert repos.set_hashes == [(old.id, "upgraded")]

    current = owner(password_hash=generate_password_hash(PASSWORD, method="scrypt"))
    service, _, repos, _, _, _ = make_login(account=current, use_werkzeug_rehash=True)
    service.login(username="Owner", password=PASSWORD, client_ip="192.0.2.1")
    assert repos.set_hashes == []


def test_login_rehashes_legacy_pbkdf2_hash_to_configured_scrypt():
    legacy = owner(password_hash="pbkdf2:sha256:600000$salt$encoded")
    service, _, repos, _, _, verified = make_login(
        account=legacy,
        use_werkzeug_rehash=True,
        hash_fn=lambda _: "new-scrypt-hash",
    )

    service.login(username="Owner", password=PASSWORD, client_ip="192.0.2.1")

    assert verified == [(PASSWORD, legacy.password_hash)]
    assert repos.set_hashes == [(legacy.id, "new-scrypt-hash")]


def test_session_creation_failure_rolls_back_without_success_reset():
    service, uow, _, _, throttle, _ = make_login(
        account=owner(), sessions=Sessions(fail_create=True)
    )
    with pytest.raises(RuntimeError, match="session write failure"):
        service.login(username="Owner", password=PASSWORD, client_ip="192.0.2.1")
    assert uow.rollbacks == 1 and throttle.successes == []


def test_unexpected_login_failure_releases_reserved_throttle_capacity():
    from huginn.management.application.throttling.failed_login import (
        FailedLoginThrottle,
    )

    throttle = FailedLoginThrottle(max_failures=1)

    def fail_verification(*_):
        raise RuntimeError("verifier unavailable")

    service, *_ = make_login(
        account=owner(), throttle=throttle, verify=fail_verification
    )

    with pytest.raises(RuntimeError, match="verifier unavailable"):
        service.login(username="Owner", password=PASSWORD, client_ip="192.0.2.1")

    reservation = throttle.reserve("192.0.2.1", "Owner")
    throttle.release(reservation)


def make_password_change(
    *,
    valid=True,
    fail_hash=False,
    fail_set=False,
    fail_revoke=False,
    fail_commit=False,
    account_value=...,
):
    if account_value is ...:
        account_value = owner()
    uow, repos, sessions, checked = (
        Uow(fail_commit),
        Accounts(account_value, fail_set),
        Sessions(fail_revoke=fail_revoke),
        [],
    )

    def verifier(password, encoded):
        checked.append((password.value, encoded))
        return valid

    def hasher(password):
        if fail_hash:
            raise RuntimeError("hash failure")
        return f"new:{password.value}"

    service = AuthenticationService(
        lambda: uow,
        config=ManagementConfig("postgresql://ignored"),
        throttle=Throttle(),
        accounts_factory=lambda _: repos,
        sessions_factory=lambda _: sessions,
        clock=lambda: NOW,
        verify_password_fn=verifier,
        hash_password_fn=hasher,
    )
    return service, account_value, uow, repos, sessions, checked


def test_password_change_requires_current_password_and_active_account():
    service, account_value, uow, repos, sessions, checked = make_password_change(
        valid=False
    )
    with pytest.raises(AuthenticationError, match="^current password is incorrect$"):
        service.change_password(
            account_value.id,
            current_password=PASSWORD,
            new_password="new secure password",
        )
    assert checked == [(PASSWORD, "stored-hash")]
    assert repos.set_hashes == [] and sessions.revoked == []
    assert uow.rollbacks == 1 and uow.commits == 0

    for missing in (None, owner("disabled")):
        service, account_value, _, _, _, checked = make_password_change(
            account_value=missing
        )
        with pytest.raises(
            AuthenticationError, match="^current password is incorrect$"
        ):
            service.change_password(
                uuid4() if account_value is None else account_value.id,
                current_password=PASSWORD,
                new_password="new secure password",
            )
        assert checked == []


def test_password_change_hashes_and_revokes_all_sessions_in_one_transaction():
    service, account_value, uow, repos, sessions, checked = make_password_change()
    service.change_password(
        account_value.id, current_password=PASSWORD, new_password="new secure password"
    )
    assert checked == [(PASSWORD, "stored-hash")]
    assert repos.set_hashes == [(account_value.id, "new:new secure password")]
    assert repos.id_locked_lookups == [account_value.id]
    assert sessions.revoked == [(account_value.id, NOW)]
    assert uow.commits == 1 and uow.rollbacks == 0


@pytest.mark.parametrize(
    "failure", ["hash", "password_write", "session_revoke", "commit"]
)
def test_password_change_rolls_back_each_failure(failure):
    service, account_value, uow, _, _, _ = make_password_change(
        fail_hash=failure == "hash",
        fail_set=failure == "password_write",
        fail_revoke=failure == "session_revoke",
        fail_commit=failure == "commit",
    )
    with pytest.raises(RuntimeError):
        service.change_password(
            account_value.id,
            current_password=PASSWORD,
            new_password="new secure password",
        )
    assert uow.rollbacks == 1
