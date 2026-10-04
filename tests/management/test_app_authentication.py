"""Shared fake services for management boundary tests.

The former Flask authentication boundary tests are covered by the FastAPI core,
session, and router tests. This module keeps their reusable fixture builders.
"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from huginn.management.app import create_app
from huginn.management.config import ManagementConfig
from huginn.management.domain.entities.session import Session
from huginn.management.domain.value_objects.common import Principal
from huginn.management.security.tokens import digest_token

SESSION_TOKEN = "raw-session-token-sentinel"
CSRF_TOKEN = "raw-csrf-token-sentinel"
NOW = datetime(2099, 10, 2, tzinfo=UTC)


class FakeUnitOfWork:
    def __init__(self):
        self.connection = object()
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        self.commits += 1


class FakeSessions:
    def __init__(self, *, status="active"):
        self.account_id, self.user_id = uuid4(), uuid4()
        self.row = Session(
            uuid4(),
            self.account_id,
            digest_token(SESSION_TOKEN),
            digest_token(CSRF_TOKEN),
            NOW,
            NOW + timedelta(hours=1),
            None,
        )
        self.status = status
        self.calls = []

    def get_by_token_digest(self, digest):
        self.calls.append(("session", digest))
        return self.row if self.row.token_digest == digest else None

    def get_active_principal_by_token_digest(self, digest, now):
        self.calls.append(("principal", digest))
        if (
            self.row.token_digest == digest
            and self.row.revoked_at is None
            and self.row.expires_at > now
            and self.status == "active"
        ):
            return Principal(self.account_id, self.user_id)
        return None

    def revoke_current(self, session_id, revoked_at):
        self.row = replace(self.row, revoked_at=revoked_at)


class FakeLogin:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    def login(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


class FakePasswordChange:
    def __init__(self, error=None):
        self.error, self.calls = error, []

    def change_password(self, account_id, **kwargs):
        self.calls.append((account_id, kwargs))
        if self.error:
            raise self.error


def make_app(
    sessions=None,
    *,
    login=None,
    password_change=None,
    user_profile_service=None,
    service_offering_service=None,
    ideal_client_profile_service=None,
    discovery_strategy_service=None,
    config=None,
):
    repository = sessions or FakeSessions()
    uow = FakeUnitOfWork()
    app = create_app(
        config or ManagementConfig("unused", environment="test"),
        readiness=type("Ready", (), {"is_ready": lambda self: True})(),
        unit_of_work_factory=lambda: uow,
        sessions_factory=lambda _uow: repository,
        login_service=login,
        password_change_service=password_change,
        user_profile_service=user_profile_service,
        service_offering_service=service_offering_service,
        ideal_client_profile_service=ideal_client_profile_service,
        discovery_strategy_service=discovery_strategy_service,
        clock=lambda: datetime.now(UTC),
    )
    return app, repository, uow
