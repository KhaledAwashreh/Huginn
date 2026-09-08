from __future__ import annotations

import pytest

from huginn.ingestion.adapters import yc
from huginn.ingestion.ports import ApiSourcePort


def test_yc_directory_adapter_explicitly_implements_api_source_port():
    assert ApiSourcePort in yc.YcDirectoryAdapter.__mro__


def test_yc_directory_adapter_source_and_mechanism_unchanged():
    adapter = yc.YcDirectoryAdapter()
    assert adapter.source == "yc"
    assert adapter.mechanism == "api"


def test_yc_directory_adapter_fetch_still_not_implemented():
    adapter = yc.YcDirectoryAdapter()
    with pytest.raises(NotImplementedError):
        adapter.fetch()


def test_algolia_api_key_reads_env_var(monkeypatch):
    monkeypatch.setenv(yc.ALGOLIA_API_KEY_ENV_VAR, "test-secured-key")

    assert yc._algolia_api_key() == "test-secured-key"


def test_algolia_api_key_raises_when_unset(monkeypatch):
    monkeypatch.delenv(yc.ALGOLIA_API_KEY_ENV_VAR, raising=False)

    try:
        yc._algolia_api_key()
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert yc.ALGOLIA_API_KEY_ENV_VAR in str(exc)


def test_algolia_api_key_raises_when_empty(monkeypatch):
    monkeypatch.setenv(yc.ALGOLIA_API_KEY_ENV_VAR, "")

    try:
        yc._algolia_api_key()
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert yc.ALGOLIA_API_KEY_ENV_VAR in str(exc)
