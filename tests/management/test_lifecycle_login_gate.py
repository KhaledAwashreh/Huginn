from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from huginn.management.application.errors.errors import AuthenticationError
from huginn.management.application.errors.lifecycle import LifecycleIntegrityError
from tests.management.test_authentication_services import (
    GENERIC_FAILURE,
    PASSWORD,
    make_login,
    owner,
)


def test_pending_public_account_cannot_issue_session_even_with_correct_password():
    service, uow, _, sessions, _, _ = make_login(
        account=owner(),
        recovery_identity=SimpleNamespace(
            verification_required=True, verified_email=None
        ),
    )
    with pytest.raises(AuthenticationError, match=GENERIC_FAILURE):
        service.login(username="Owner", password=PASSWORD, client_ip="192.0.2.1")
    assert sessions.created == []
    assert uow.commits == 0


def test_missing_recovery_identity_fails_closed():
    service, _, _, sessions, _, _ = make_login(account=owner(), recovery_identity=None)
    with pytest.raises(LifecycleIntegrityError):
        service.login(username="Owner", password=PASSWORD, client_ip="192.0.2.1")
    assert sessions.created == []


def test_verified_public_account_can_log_in():
    service, _, _, sessions, _, _ = make_login(
        account=owner(),
        recovery_identity=SimpleNamespace(
            verification_required=True,
            verified_email="verified@example.test",
            verified_at=datetime.now(UTC),
        ),
    )
    service.login(username="Owner", password=PASSWORD, client_ip="192.0.2.1")
    assert len(sessions.created) == 1
