from __future__ import annotations

from huginn.bronze.api_ingest_store import PostgresApiIngestStore
from huginn.config import Config
from huginn.ingestion.__main__ import build_service
from huginn.ingestion.adapters.hn import HackerNewsAdapter
from huginn.ingestion.adapters.yc import YcDirectoryAdapter
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
    assert service._raw_store._database_url == config.database_url
    assert isinstance(service._job_run_writer, PostgresJobRunWriter)
    assert service._job_run_writer._database_url == config.database_url
