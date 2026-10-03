import pytest
from fastapi.testclient import TestClient

from huginn.management import app as app_module
from huginn.management.config import ManagementConfig


class FakeReadiness:
    def __init__(self, ready: bool):
        self.ready = ready
        self.calls = 0

    def is_ready(self) -> bool:
        self.calls += 1
        return self.ready


def test_health_does_not_probe_the_database():
    probe = FakeReadiness(False)
    app = app_module.create_app(ManagementConfig("unused"), readiness=probe)

    assert probe.calls == 0
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["content-type"].startswith("application/json")
    assert "set-cookie" not in response.headers
    assert probe.calls == 0


@pytest.mark.parametrize(("is_ready", "status"), ((True, 200), (False, 503)))
def test_ready_probes_once_and_returns_status(is_ready, status):
    probe = FakeReadiness(is_ready)
    app = app_module.create_app(ManagementConfig("unused"), readiness=probe)

    response = TestClient(app).get("/ready")

    assert response.status_code == status
    assert response.json() == {"status": "ready" if is_ready else "not_ready"}
    assert response.headers["content-type"].startswith("application/json")
    assert "set-cookie" not in response.headers
    assert probe.calls == 1


def test_factory_constructs_default_probe_without_probing(monkeypatch):
    constructed_with = []

    class InertProbe:
        def __init__(self, database_url):
            constructed_with.append(database_url)

        def is_ready(self):
            pytest.fail("application creation probed Postgres")

    monkeypatch.setattr(app_module, "PostgresReadiness", InertProbe)
    app_module.create_app(ManagementConfig("postgresql://management.test/huginn"))

    assert constructed_with == ["postgresql://management.test/huginn"]


def test_app_construction_and_health_do_not_create_database_adapter(monkeypatch):
    def unexpected_connection_factory(*args, **kwargs):
        pytest.fail("application construction attempted to create a database adapter")

    monkeypatch.setattr(
        app_module, "ManagementConnectionFactory", unexpected_connection_factory
    )
    app = app_module.create_app(
        ManagementConfig("postgresql://management.test/huginn"),
        readiness=FakeReadiness(True),
    )

    assert TestClient(app).get("/health").status_code == 200


def test_injected_probes_are_independent_between_factories(monkeypatch):
    def unexpected_load_config():
        pytest.fail("injected configuration was ignored")

    def unexpected_default_probe(*args, **kwargs):
        pytest.fail("injected readiness probe was ignored")

    monkeypatch.setattr(app_module, "load_config", unexpected_load_config)
    monkeypatch.setattr(app_module, "PostgresReadiness", unexpected_default_probe)
    first_probe, second_probe = FakeReadiness(True), FakeReadiness(False)
    config = ManagementConfig("unused")
    first_app = app_module.create_app(config, readiness=first_probe)
    second_app = app_module.create_app(config, readiness=second_probe)

    assert TestClient(first_app).get("/ready").status_code == 200
    assert first_probe.calls == 1
    assert second_probe.calls == 0
    assert TestClient(second_app).get("/ready").status_code == 503
    assert first_probe.calls == 1
    assert second_probe.calls == 1


def test_missing_config_raises_before_constructing_probe(monkeypatch):
    def missing_config():
        raise RuntimeError("HUGINN_MANAGEMENT_DATABASE_URL is not set")

    def unexpected_probe(*args, **kwargs):
        pytest.fail("probe constructed after configuration failure")

    monkeypatch.setattr(app_module, "load_config", missing_config)
    monkeypatch.setattr(app_module, "PostgresReadiness", unexpected_probe)

    with pytest.raises(
        RuntimeError, match=r"^HUGINN_MANAGEMENT_DATABASE_URL is not set$"
    ):
        app_module.create_app()


def test_management_routes_are_registered():
    app = app_module.create_app(
        ManagementConfig("unused"), readiness=FakeReadiness(True)
    )
    routes = {
        (path, method.upper())
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    }

    assert routes == {
        ("/health", "GET"),
        ("/ready", "GET"),
        ("/api/v1/sessions", "POST"),
        ("/api/v1/sessions/current", "DELETE"),
        ("/api/v1/me/password", "PATCH"),
        ("/api/v1/me", "GET"),
        ("/api/v1/me", "PATCH"),
        ("/api/v1/me/professional-profile", "GET"),
        ("/api/v1/me/professional-profile", "PATCH"),
        ("/api/v1/offerings", "GET"),
        ("/api/v1/offerings", "POST"),
        ("/api/v1/offerings/{offering_id}", "GET"),
        ("/api/v1/offerings/{offering_id}", "PATCH"),
        ("/api/v1/offerings/{offering_id}", "DELETE"),
        ("/api/v1/ideal-client-profiles", "GET"),
        ("/api/v1/ideal-client-profiles", "POST"),
        ("/api/v1/ideal-client-profiles/{profile_id}", "GET"),
        ("/api/v1/ideal-client-profiles/{profile_id}", "PATCH"),
        ("/api/v1/ideal-client-profiles/{profile_id}", "DELETE"),
        ("/api/v1/discovery-strategies", "GET"),
        ("/api/v1/discovery-strategies", "POST"),
        ("/api/v1/discovery-strategies/{strategy_id}", "GET"),
        ("/api/v1/discovery-strategies/{strategy_id}", "PATCH"),
        ("/api/v1/discovery-strategies/{strategy_id}", "DELETE"),
    }


@pytest.mark.parametrize("path", ("/health", "/ready"))
def test_application_routes_reject_post(path):
    app = app_module.create_app(
        ManagementConfig("unused"), readiness=FakeReadiness(True)
    )
    assert TestClient(app).post(path).status_code == 405


@pytest.mark.parametrize("path", ("/", "/accounts", "/ready/accounts"))
def test_unregistered_routes_return_not_found(path):
    app = app_module.create_app(
        ManagementConfig("unused"), readiness=FakeReadiness(True)
    )
    assert TestClient(app).get(path).status_code == 404
