from datetime import timedelta

import pytest

from huginn.management import config


@pytest.fixture(autouse=True)
def disable_dotenv(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda: False)


def test_load_config_reads_management_database_url_only(monkeypatch):
    management_url = "postgresql://manager:secret@management.test/huginn"
    monkeypatch.setenv("HUGINN_MANAGEMENT_DATABASE_URL", management_url)
    monkeypatch.setenv(
        "HUGINN_DATABASE_URL",
        "postgresql://elt:secret@elt.test/huginn",
    )

    loaded = config.load_config()

    assert loaded.database_url == management_url


def test_load_config_strips_management_database_url(monkeypatch):
    database_url = "postgresql://manager:secret@management.test/huginn"
    monkeypatch.setenv(
        "HUGINN_MANAGEMENT_DATABASE_URL",
        f" \t{database_url}\n",
    )

    loaded = config.load_config()

    assert loaded.database_url == database_url


@pytest.mark.parametrize("value", (None, "", " ", "\t", "\n"))
def test_load_config_rejects_missing_or_blank_management_url(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("HUGINN_MANAGEMENT_DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("HUGINN_MANAGEMENT_DATABASE_URL", value)
    monkeypatch.setenv(
        "HUGINN_DATABASE_URL",
        "postgresql://elt:secret@elt.test/huginn",
    )

    with pytest.raises(
        RuntimeError,
        match=r"^HUGINN_MANAGEMENT_DATABASE_URL is not set$",
    ):
        config.load_config()


def test_management_config_hides_database_url_from_repr():
    database_url = "postgresql://manager:secret@management.test/huginn"

    rendered = repr(config.ManagementConfig(database_url=database_url))

    assert database_url not in rendered
    assert "secret" not in rendered


def test_management_config_cookie_defaults_and_production_security():
    config_value = config.ManagementConfig("unused")
    production = config.ManagementConfig("unused", environment="production")

    assert config_value.cookie_name == "huginn_management_session"
    assert config_value.cookie_secure is False
    assert config_value.cookie_samesite == "Lax"
    assert config_value.session_ttl == timedelta(hours=12)
    assert config_value.login_throttle_failures == 5
    assert config_value.login_throttle_window == timedelta(minutes=15)
    assert production.cookie_secure is True


@pytest.mark.parametrize(
    "kwargs",
    (
        {"cookie_name": "bad name"},
        {"cookie_samesite": "unsafe"},
        {"session_ttl": timedelta(0)},
        {"login_throttle_failures": 0},
        {"login_throttle_window": timedelta(0)},
        {"environment": "production", "cookie_secure": False},
        {"cookie_secure": "false"},
    ),
)
def test_management_config_rejects_invalid_auth_settings(kwargs):
    with pytest.raises(ValueError):
        config.ManagementConfig("unused", **kwargs)


def test_load_config_auth_settings_and_dsn_safe_repr(monkeypatch):
    monkeypatch.setenv("HUGINN_MANAGEMENT_DATABASE_URL", "postgresql://u:p@host/db")
    monkeypatch.setenv("HUGINN_MANAGEMENT_ENVIRONMENT", "production")
    monkeypatch.setenv("HUGINN_MANAGEMENT_COOKIE_SAMESITE", "Strict")
    monkeypatch.setenv("HUGINN_MANAGEMENT_SESSION_TTL_SECONDS", "3600")

    loaded = config.load_config()

    assert loaded.cookie_secure is True
    assert loaded.cookie_samesite == "Strict"
    assert loaded.session_ttl == timedelta(hours=1)
    assert "postgresql://u:p@host/db" not in repr(loaded)


@pytest.mark.parametrize(
    ("key", "value"),
    (
        ("HUGINN_MANAGEMENT_COOKIE_SAMESITE", "unsafe"),
        ("HUGINN_MANAGEMENT_ENVIRONMENT", "unknown"),
        ("HUGINN_MANAGEMENT_LOGIN_THROTTLE_FAILURES", "many"),
        ("HUGINN_MANAGEMENT_SESSION_TTL_SECONDS", "0"),
    ),
)
def test_load_config_rejects_invalid_auth_environment(monkeypatch, key, value):
    monkeypatch.setenv("HUGINN_MANAGEMENT_DATABASE_URL", "postgresql://host/db")
    monkeypatch.setenv(key, value)
    with pytest.raises(RuntimeError, match="^invalid management configuration$"):
        config.load_config()
