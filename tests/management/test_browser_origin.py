from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from tests.management.test_app_authentication import NOW, FakeLogin, make_app


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://evil.test"},
        {"Origin": "null"},
        {"Origin": "http://testserver/"},
        {"Origin": "http://testserver/path"},
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
        {"Origin": "https://evil.test", "Sec-Fetch-Site": "same-origin"},
    ],
)
def test_browser_login_rejects_untrusted_origin_before_credentials(headers):
    service = FakeLogin()
    app, _, _ = make_app(login=service)
    with TestClient(app) as client:
        result = client.post(
            "/api/v1/sessions",
            json={"username": "Owner", "password": "long enough password"},
            headers=headers,
        )
    assert result.status_code == 403
    assert service.calls == []


@pytest.mark.parametrize(
    "headers", [{}, {"Origin": "http://testserver", "Sec-Fetch-Site": "same-origin"}]
)
def test_same_origin_and_trusted_operator_login_work(headers):
    service = FakeLogin(
        SimpleNamespace(
            session_token="secret",
            csrf_token="proof",
            expires_at=NOW + timedelta(hours=1),
        )
    )
    app, _, _ = make_app(login=service)
    with TestClient(app) as client:
        result = client.post(
            "/api/v1/sessions",
            json={"username": "Owner", "password": "long enough password"},
            headers=headers,
        )
    assert result.status_code == 200
    assert len(service.calls) == 1


def test_login_requires_json_before_credentials():
    service = FakeLogin()
    app, _, _ = make_app(login=service)
    with TestClient(app) as client:
        result = client.post(
            "/api/v1/sessions",
            content='{"username":"Owner","password":"long enough password"}',
            headers={"Content-Type": "text/plain"},
        )
    assert result.status_code == 403
    assert service.calls == []


def test_origin_comparison_preserves_explicit_zero_port():
    from huginn.management.presentation.api.dependencies.browser_origin import _origin

    assert _origin("http://testserver:0") != _origin("http://testserver")
