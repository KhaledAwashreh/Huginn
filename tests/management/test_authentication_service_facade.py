from datetime import UTC, datetime, timedelta
from uuid import uuid4

from huginn.management.domain.common import Principal
from huginn.management.domain.session import Session
from huginn.management.security.tokens import digest_token
from huginn.management.services.authentication import AuthenticationService


class UnitOfWork:
    def __init__(self):
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        self.commits += 1


class Sessions:
    def __init__(self, principal, session):
        self.principal, self.session = principal, session
        self.lookups, self.revocations = [], []

    def get_active_principal_by_token_digest(self, digest, now):
        self.lookups.append((digest, now))
        return self.principal

    def get_by_token_digest(self, digest):
        self.lookups.append((digest, None))
        return self.session if digest == self.session.token_digest else None

    def revoke_current(self, session_id, at):
        self.revocations.append((session_id, at))


def test_authentication_service_owns_session_resolution_logout_and_password_entrypoints():
    now = datetime(2026, 1, 2, tzinfo=UTC)
    principal = Principal(uuid4(), uuid4())
    session = Session(
        uuid4(),
        principal.account_id,
        digest_token("opaque-token"),
        "csrf",
        now,
        now + timedelta(hours=1),
        None,
    )
    sessions = Sessions(principal, session)
    uow = UnitOfWork()
    service = AuthenticationService(
        lambda: uow,
        config=None,
        throttle=None,
        sessions_factory=lambda _: sessions,
        clock=lambda: now,
    )

    assert service.authenticate("opaque-token") == principal
    service.logout("opaque-token")

    assert sessions.lookups[0][0] != "opaque-token"
    assert sessions.revocations == [(session.id, now)]
    assert uow.commits == 1
