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
