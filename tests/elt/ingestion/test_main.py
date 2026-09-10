from __future__ import annotations

import pytest

from huginn.config import Config
from huginn.elt.bronze.api_ingest_store import PostgresApiIngestStore
from huginn.elt.bronze.repositories.api_ingest_repository import (
    PostgresApiIngestRepository,
)
from huginn.elt.ingestion import __main__ as main_module
from huginn.elt.ingestion.__main__ import build_service, main
from huginn.elt.ingestion.adapters.hn import HackerNewsAdapter
from huginn.elt.ingestion.adapters.yc import YcDirectoryAdapter
from huginn.ops.postgres_job_run_writer import PostgresJobRunWriter


def test_build_service_wires_both_adapters():
    config = Config(database_url="postgresql://example.invalid/db")

    service = build_service(config)

    assert [type(source) for source in service._sources] == [
        HackerNewsAdapter,
        YcDirectoryAdapter,
    ]


def test_build_service_wires_postgres_backed_ports_with_the_configured_url():
    config = Config(database_url="postgresql://example.invalid/db")

    service = build_service(config)

    assert isinstance(service._raw_store, PostgresApiIngestStore)
    # The store now holds a repository rather than a URL: the configured
    # URL reaches bronze.api_ingest through that one injected object.
    assert isinstance(service._raw_store._repository, PostgresApiIngestRepository)
    assert service._raw_store._repository._database_url == config.database_url
    assert isinstance(service._job_run_writer, PostgresJobRunWriter)
    assert service._job_run_writer._database_url == config.database_url


class FakeService:
    def __init__(self, failed_count: int) -> None:
        self._failed_count = failed_count

    def run_once(self) -> int:
        return self._failed_count


def test_main_exits_zero_when_every_source_succeeds(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "load_config",
        lambda: Config(database_url="postgresql://example.invalid/db"),
    )
    monkeypatch.setattr(
        main_module, "build_service", lambda config: FakeService(failed_count=0)
    )

    main()  # must not raise SystemExit


def test_main_exits_non_zero_when_a_source_failed(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "load_config",
        lambda: Config(database_url="postgresql://example.invalid/db"),
    )
    monkeypatch.setattr(
        main_module, "build_service", lambda config: FakeService(failed_count=1)
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
