"""Direct tests for `load_config()`.

The one place outside the isolation guard's own file that names
HUGINN_DATABASE_URL, and deliberately so: `load_config()` reads the database
variable before the Algolia key, so testing either branch means setting and
asserting on both names. It is listed in the guard's `_ALLOWED_FILES` for that
reason, and the guard asserts in turn that this file names no driver, no
container library, and no connection fixture, so it cannot reach a database.
See tests/test_integration_database_isolation.py.
"""

from __future__ import annotations

import pytest

from huginn.config import load_config


def _clear(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HUGINN_DATABASE_URL", raising=False)
    monkeypatch.delenv("HUGINN_YC_ALGOLIA_API_KEY", raising=False)


def test_load_config_returns_database_url_and_algolia_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("HUGINN_DATABASE_URL", "postgresql://example.invalid/huginn")
    monkeypatch.setenv("HUGINN_YC_ALGOLIA_API_KEY", "key-blob")

    config = load_config()

    assert config.database_url == "postgresql://example.invalid/huginn"
    assert config.yc_algolia_api_key == "key-blob"


def test_load_config_raises_naming_database_url_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("HUGINN_YC_ALGOLIA_API_KEY", "key-blob")

    with pytest.raises(RuntimeError, match="HUGINN_DATABASE_URL is not set"):
        load_config()


def test_load_config_raises_naming_algolia_key_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("HUGINN_DATABASE_URL", "postgresql://example.invalid/huginn")

    with pytest.raises(
        RuntimeError,
        match="HUGINN_YC_ALGOLIA_API_KEY is not set. Copy .env.example to .env",
    ):
        load_config()


def test_load_config_raises_naming_algolia_key_when_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("HUGINN_DATABASE_URL", "postgresql://example.invalid/huginn")
    monkeypatch.setenv("HUGINN_YC_ALGOLIA_API_KEY", "")

    with pytest.raises(RuntimeError, match="HUGINN_YC_ALGOLIA_API_KEY is not set"):
        load_config()
