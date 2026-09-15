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
from huginn.elt.ingestion.adapters.opencorporates import OpenCorporatesAdapter
from huginn.elt.ingestion.adapters.yc import YcDirectoryAdapter
from huginn.ops.postgres_job_run_writer import PostgresJobRunWriter


class _FakeCompanyRepository:
    """Stands in for `PostgresCompanyRepository` so `build_service` is
    testable without a live database (CLAUDE.md code standard 4): its
    `__enter__` never opens a real connection.
    """

    def __init__(self, database_url: str) -> None:
        """Capture the URL that production wiring passes to the repository."""
        self.database_url = database_url

    def __enter__(self):
        """Return the database-free repository double."""
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """Leave the database-free repository context without suppression."""
        return None

    def read_unenriched_company_names(self, limit: int) -> list[str]:
        """Return candidates while recording the requested run budget."""
        self.requested_limit = limit
        return ["Acme Robotics", "Beta Corp"]


def test_build_service_wires_all_three_adapters(monkeypatch):
    """The service includes HN, YC, and OpenCorporates adapters."""
    monkeypatch.setattr(
        main_module, "PostgresCompanyRepository", _FakeCompanyRepository
    )
    config = Config(database_url="postgresql://example.invalid/db")

    service = build_service(config)

    assert [type(source) for source in service._sources] == [
        HackerNewsAdapter,
        YcDirectoryAdapter,
        OpenCorporatesAdapter,
    ]


def test_build_service_wires_opencorporates_from_the_gold_unenriched_read(monkeypatch):
    """OpenCorporates loads a bounded candidate set lazily from Gold."""
    repositories = []

    def fake_company_repository(database_url):
        """Create and retain the repository double for wiring assertions."""
        fake_repository = _FakeCompanyRepository(database_url)
        repositories.append(fake_repository)
        return fake_repository

    monkeypatch.setattr(
        main_module, "PostgresCompanyRepository", fake_company_repository
    )
    config = Config(database_url="postgresql://example.invalid/db")

    service = build_service(config)

    assert repositories == []
    opencorporates_adapter = service._sources[2]
    assert opencorporates_adapter._max_calls == main_module.OPENCORPORATES_MAX_CALLS
    monkeypatch.setattr(
        main_module,
        "_search_companies",
        lambda name: {"results": {"companies": []}},
        raising=False,
    )
    monkeypatch.setattr(
        "huginn.elt.ingestion.adapters.opencorporates._search_companies",
        lambda name: {"results": {"companies": []}},
    )
    opencorporates_adapter.fetch()

    assert len(repositories) == 1
    fake_repository = repositories[0]
    assert fake_repository.database_url == config.database_url
    assert fake_repository.requested_limit == main_module.OPENCORPORATES_MAX_CALLS


def test_build_service_wires_postgres_backed_ports_with_the_configured_url(monkeypatch):
    """Postgres-backed ports receive the configured database URL."""
    monkeypatch.setattr(
        main_module, "PostgresCompanyRepository", _FakeCompanyRepository
    )
    config = Config(database_url="postgresql://example.invalid/db")

    service = build_service(config)

    assert isinstance(service._raw_store, PostgresApiIngestStore)
    # The store now holds a repository rather than a URL: the configured
    # URL reaches bronze.api_ingest through that one injected object.
    assert isinstance(service._raw_store._repository, PostgresApiIngestRepository)
    assert service._raw_store._repository._database_url == config.database_url
    assert service._raw_store._stable_fields_by_source == {
        "opencorporates": OpenCorporatesAdapter.stable_fields
    }
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
