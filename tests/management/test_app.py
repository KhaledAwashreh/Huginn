import pytest

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
    response = app.test_client().get("/health")

    assert response.status_code == 200
    assert response.data == b'{"status":"ok"}\n'
    assert response.json == {"status": "ok"}
    assert response.mimetype == "application/json"
    assert "Set-Cookie" not in response.headers
    assert probe.calls == 0


@pytest.mark.parametrize(
    ("is_ready", "status_code", "body"),
    (
        (True, 200, b'{"status":"ready"}\n'),
        (False, 503, b'{"status":"not_ready"}\n'),
    ),
)
def test_ready_probes_once_and_returns_exact_response(is_ready, status_code, body):
    probe = FakeReadiness(is_ready)
    app = app_module.create_app(ManagementConfig("unused"), readiness=probe)

    response = app.test_client().get("/ready")

    assert response.status_code == status_code
    assert response.data == body
    assert response.json == {
        "status": "ready" if is_ready else "not_ready",
    }
    assert response.mimetype == "application/json"
    assert "Set-Cookie" not in response.headers
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


def test_injected_probes_are_independent_between_factories(monkeypatch):
    def unexpected_load_config():
        pytest.fail("injected configuration was ignored")

    def unexpected_default_probe(*args, **kwargs):
        pytest.fail("injected readiness probe was ignored")

    monkeypatch.setattr(app_module, "load_config", unexpected_load_config)
    monkeypatch.setattr(app_module, "PostgresReadiness", unexpected_default_probe)
    first_probe = FakeReadiness(True)
    second_probe = FakeReadiness(False)
    config = ManagementConfig("unused")

    first_app = app_module.create_app(config, readiness=first_probe)
    second_app = app_module.create_app(config, readiness=second_probe)

    assert first_app.test_client().get("/ready").status_code == 200
    assert first_probe.calls == 1
    assert second_probe.calls == 0
    assert second_app.test_client().get("/ready").status_code == 503
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
        RuntimeError,
        match=r"^HUGINN_MANAGEMENT_DATABASE_URL is not set$",
    ):
        app_module.create_app()


def test_only_health_and_readiness_routes_are_registered():
    app = app_module.create_app(
        ManagementConfig("unused"),
        readiness=FakeReadiness(True),
    )

    routes = {(rule.rule, frozenset(rule.methods)) for rule in app.url_map.iter_rules()}

    assert routes == {
        ("/health", frozenset({"GET", "HEAD", "OPTIONS"})),
        ("/ready", frozenset({"GET", "HEAD", "OPTIONS"})),
    }


@pytest.mark.parametrize("path", ("/health", "/ready"))
def test_application_routes_reject_post(path):
    app = app_module.create_app(
        ManagementConfig("unused"),
        readiness=FakeReadiness(True),
    )

    assert app.test_client().post(path).status_code == 405


@pytest.mark.parametrize("path", ("/", "/accounts", "/ready/accounts"))
def test_unregistered_routes_return_not_found(path):
    app = app_module.create_app(
        ManagementConfig("unused"),
        readiness=FakeReadiness(True),
    )

    assert app.test_client().get(path).status_code == 404
