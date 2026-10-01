from __future__ import annotations

import logging

import pytest

from huginn.config import Config
from huginn.elt.bronze.api_ingest_store import PostgresApiIngestStore
from huginn.elt.bronze.repositories.api_ingest_repository import (
    PostgresApiIngestRepository,
)
from huginn.elt.bronze.repositories.eu_startups_discovery_repository import (
    PostgresEuStartupsDiscoveryRepository,
)
from huginn.elt.bronze.repositories.eu_startups_enrichment_repository import (
    PostgresEuStartupsEnrichmentRepository,
)
from huginn.elt.ingestion import __main__ as main_module
from huginn.elt.ingestion.__main__ import (
    build_eu_startups_discovery_runner,
    build_service,
    main,
)
from huginn.elt.ingestion.adapters import yc
from huginn.elt.ingestion.adapters.eu_startups import EuStartupsDiscoveryAdapter
from huginn.elt.ingestion.adapters.eu_startups_enrichment import (
    EuStartupsEnrichmentAdapter,
)
from huginn.elt.ingestion.adapters.hn import HackerNewsAdapter
from huginn.elt.ingestion.adapters.opencorporates import OpenCorporatesAdapter
from huginn.elt.ingestion.adapters.yc import YcDirectoryAdapter
from huginn.elt.ingestion.connectors import firebase
from huginn.elt.ingestion.connectors.algolia import AlgoliaConnector
from huginn.elt.ingestion.connectors.firebase import FirebaseConnector
from huginn.elt.ingestion.eu_startups_discovery_runner import (
    EuStartupsDiscoveryRunner,
)
from huginn.elt.ingestion.eu_startups_enrichment_runner import (
    EuStartupsEnrichmentRunner,
)
from huginn.elt.stage_runner import Stage
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
    config = Config(
        database_url="postgresql://example.invalid/db",
        yc_algolia_api_key="key-blob",
    )

    service = build_service(config)

    assert [type(source) for source in service._sources] == [
        HackerNewsAdapter,
        YcDirectoryAdapter,
        OpenCorporatesAdapter,
    ]


def test_build_service_injects_a_configured_algolia_connector(monkeypatch):
    """The YC adapter receives a real AlgoliaConnector built from config."""
    monkeypatch.setattr(
        main_module, "PostgresCompanyRepository", _FakeCompanyRepository
    )
    config = Config(
        database_url="postgresql://example.invalid/db",
        yc_algolia_api_key="key-blob",
    )

    service = build_service(config)

    yc_adapter = service._sources[1]
    connector = yc_adapter._algolia
    assert isinstance(connector, AlgoliaConnector)
    assert connector._app_id == yc.YC_ALGOLIA_APP_ID
    assert connector._index == yc.YC_ALGOLIA_INDEX
    assert connector._api_key == config.yc_algolia_api_key


def test_build_service_injects_a_firebase_connector(monkeypatch):
    """The HN adapter receives a real FirebaseConnector."""
    monkeypatch.setattr(
        main_module, "PostgresCompanyRepository", _FakeCompanyRepository
    )
    config = Config(
        database_url="postgresql://example.invalid/db",
        yc_algolia_api_key="key-blob",
    )

    service = build_service(config)

    hn_adapter = service._sources[0]
    assert isinstance(hn_adapter._firebase, FirebaseConnector)
    assert hn_adapter._firebase._timeout == firebase.DEFAULT_TIMEOUT_SECONDS


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
    config = Config(
        database_url="postgresql://example.invalid/db",
        yc_algolia_api_key="key-blob",
    )

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
    config = Config(
        database_url="postgresql://example.invalid/db",
        yc_algolia_api_key="key-blob",
    )

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


def test_build_eu_startups_discovery_runner_wires_real_dependencies():
    config = Config(
        database_url="postgresql://example.invalid/db",
        yc_algolia_api_key="key-blob",
    )

    runner = build_eu_startups_discovery_runner(config)

    assert isinstance(runner, EuStartupsDiscoveryRunner)
    assert isinstance(runner._adapter, EuStartupsDiscoveryAdapter)
    assert isinstance(runner._repository, PostgresEuStartupsDiscoveryRepository)
    assert runner._repository._database_url == config.database_url
    assert isinstance(runner._job_run_writer, PostgresJobRunWriter)
    assert runner._job_run_writer._database_url == config.database_url


def test_build_eu_startups_enrichment_runner_wires_real_dependencies():
    config = Config(
        database_url="postgresql://example.invalid/db",
        yc_algolia_api_key="key-blob",
    )

    runner = main_module.build_eu_startups_enrichment_runner(config)

    assert isinstance(runner, EuStartupsEnrichmentRunner)
    assert isinstance(runner._adapter, EuStartupsEnrichmentAdapter)
    assert runner._adapter._max_calls == main_module.EU_STARTUPS_ENRICHMENT_MAX_CALLS
    assert isinstance(runner._repository, PostgresEuStartupsEnrichmentRepository)
    assert runner._repository._database_url == config.database_url
    assert isinstance(runner._job_run_writer, PostgresJobRunWriter)
    assert runner._job_run_writer._database_url == config.database_url


def test_enrichment_runner_loads_gold_candidates_lazily_with_the_run_limit(
    monkeypatch,
):
    repositories = []

    class FakeEnrichmentCompanyRepository(_FakeCompanyRepository):
        def read_company_names_pending_eu_startups_search(self, limit):
            self.requested_limit = limit
            return ["Brightroom"]

    def make_repository(database_url):
        repository = FakeEnrichmentCompanyRepository(database_url)
        repositories.append(repository)
        return repository

    monkeypatch.setattr(main_module, "PostgresCompanyRepository", make_repository)
    config = Config(
        database_url="postgresql://example.invalid/db",
        yc_algolia_api_key="key-blob",
    )

    runner = main_module.build_eu_startups_enrichment_runner(config)

    assert repositories == []
    assert runner._adapter._company_loader() == ["Brightroom"]
    assert (
        repositories[0].requested_limit == main_module.EU_STARTUPS_ENRICHMENT_MAX_CALLS
    )


class FakeService:
    def __init__(self, failed_count: int) -> None:
        self._failed_count = failed_count

    def run_once(self) -> int:
        return self._failed_count


class FakeDiscoveryRunner:
    def __init__(self) -> None:
        self.run_count = 0

    def run(self) -> int:
        self.run_count += 1
        return 0


def test_main_eu_discovery_command_invokes_only_the_dedicated_runner(monkeypatch):
    config = Config(
        database_url="postgresql://example.invalid/db",
        yc_algolia_api_key="key-blob",
    )
    runner = FakeDiscoveryRunner()
    monkeypatch.setattr(main_module, "load_config", lambda: config)
    monkeypatch.setattr(
        main_module,
        "build_eu_startups_discovery_runner",
        lambda actual_config: runner if actual_config is config else None,
    )
    monkeypatch.setattr(
        main_module,
        "build_service",
        lambda _config: pytest.fail("shared service must not run for EU discovery"),
    )

    main(["eu-startups-discovery"])

    assert runner.run_count == 1


def test_main_eu_enrichment_command_invokes_only_the_dedicated_runner(monkeypatch):
    config = Config(
        database_url="postgresql://example.invalid/db",
        yc_algolia_api_key="key-blob",
    )
    events = []

    class FakeEnrichmentRunner:
        def run(self):
            events.append("enrichment")
            return 2

    monkeypatch.setattr(main_module, "load_config", lambda: config)
    monkeypatch.setattr(
        main_module,
        "build_eu_startups_enrichment_runner",
        lambda actual_config: (
            FakeEnrichmentRunner() if actual_config is config else None
        ),
    )
    monkeypatch.setattr(
        main_module,
        "build_service",
        lambda _config: pytest.fail("shared service must not run for enrichment"),
    )
    monkeypatch.setattr(
        main_module,
        "build_hn_yc_sources",
        lambda _config: pytest.fail("HN/YC ingestion must not run for enrichment"),
    )
    monkeypatch.setattr(
        main_module,
        "build_eu_startups_enrichment_stages",
        lambda _config: [
            Stage(name, lambda name=name: events.append(name) or 1)
            for name in (
                "silver.eu_startups_staging",
                "silver.signal_resolution",
                "gold.company",
                "gold.company_signal",
            )
        ],
    )

    class FakeJobRunWriter:
        def write(self, _job_run):
            pass

    monkeypatch.setattr(
        main_module, "PostgresJobRunWriter", lambda _url: FakeJobRunWriter()
    )

    main(["eu-startups-enrichment"])

    assert events == [
        "enrichment",
        "silver.eu_startups_staging",
        "silver.signal_resolution",
        "gold.company",
        "gold.company_signal",
    ]


def test_main_eu_enrichment_failure_skips_every_materialization_stage(monkeypatch):
    config = Config(
        database_url="postgresql://example.invalid/db",
        yc_algolia_api_key="key-blob",
    )
    events = []

    class FailingEnrichmentRunner:
        def run(self):
            events.append("enrichment")
            raise RuntimeError("fetch/persist failed")

    monkeypatch.setattr(main_module, "load_config", lambda: config)
    monkeypatch.setattr(
        main_module,
        "build_eu_startups_enrichment_runner",
        lambda _config: FailingEnrichmentRunner(),
    )
    monkeypatch.setattr(
        main_module,
        "build_eu_startups_enrichment_stages",
        lambda _config: pytest.fail("downstream stages must not be built"),
    )
    monkeypatch.setattr(
        main_module,
        "build_service",
        lambda _config: pytest.fail("shared ingestion must not run"),
    )

    with pytest.raises(RuntimeError, match="fetch/persist failed"):
        main(["eu-startups-enrichment"])

    assert events == ["enrichment"]


def test_main_exits_non_zero_and_tracks_downstream_stage_failure(monkeypatch):
    config = Config(
        database_url="postgresql://example.invalid/db",
        yc_algolia_api_key="key-blob",
    )
    written_job_runs = []

    class FakeEnrichmentRunner:
        def run(self):
            return 0

    class FakeJobRunWriter:
        def write(self, job_run):
            written_job_runs.append(job_run)

    def fail_staging():
        raise RuntimeError("staging failed")

    monkeypatch.setattr(main_module, "load_config", lambda: config)
    monkeypatch.setattr(
        main_module,
        "build_eu_startups_enrichment_runner",
        lambda _config: FakeEnrichmentRunner(),
    )
    monkeypatch.setattr(
        main_module,
        "build_eu_startups_enrichment_stages",
        lambda _config: [
            Stage(
                "silver.eu_startups_staging",
                fail_staging,
            ),
            Stage(
                "silver.signal_resolution",
                lambda: pytest.fail("resolution depends on staging"),
                depends_on=("silver.eu_startups_staging",),
            ),
            Stage(
                "gold.company",
                lambda: pytest.fail("company materialization depends on resolution"),
                depends_on=("silver.signal_resolution",),
            ),
            Stage(
                "gold.company_signal",
                lambda: pytest.fail("company signal depends on company"),
                depends_on=("silver.signal_resolution", "gold.company"),
            ),
        ],
    )
    monkeypatch.setattr(
        main_module, "PostgresJobRunWriter", lambda _url: FakeJobRunWriter()
    )

    with pytest.raises(SystemExit) as exc_info:
        main(["eu-startups-enrichment"])

    assert exc_info.value.code == 1
    latest_status_by_stage = {
        job_run.source: job_run.status for job_run in written_job_runs
    }
    assert latest_status_by_stage == {
        "silver.eu_startups_staging": "failed",
        "silver.signal_resolution": "skipped",
        "gold.company": "skipped",
        "gold.company_signal": "skipped",
    }


def test_build_eu_startups_enrichment_stages_reuses_gold_materialization_order():
    from huginn.elt.ingestion.__main__ import build_eu_startups_enrichment_stages

    stages = build_eu_startups_enrichment_stages(
        Config(
            database_url="postgresql://example.invalid/db",
            yc_algolia_api_key="key-blob",
        )
    )

    assert [stage.name for stage in stages] == [
        "silver.eu_startups_staging",
        "silver.signal_resolution",
        "gold.company",
        "gold.company_signal",
    ]
    assert stages[1].depends_on == ("silver.eu_startups_staging",)
    assert stages[1].run.__name__ == "resolve_eu_startups"
    assert stages[2].depends_on == ("silver.signal_resolution",)
    assert stages[3].depends_on == (
        "silver.signal_resolution",
        "gold.company",
    )


def test_main_exits_zero_when_every_source_succeeds(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "load_config",
        lambda: Config(
            database_url="postgresql://example.invalid/db",
            yc_algolia_api_key="key-blob",
        ),
    )
    monkeypatch.setattr(
        main_module, "build_service", lambda config: FakeService(failed_count=0)
    )

    main()  # must not raise SystemExit


def test_main_exits_non_zero_when_a_source_failed(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "load_config",
        lambda: Config(
            database_url="postgresql://example.invalid/db",
            yc_algolia_api_key="key-blob",
        ),
    )
    monkeypatch.setattr(
        main_module, "build_service", lambda config: FakeService(failed_count=1)
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1


def test_main_logs_the_config_error_and_exits_non_zero(monkeypatch, caplog):
    """A missing required variable is logged as ERROR and exits 1, instead
    of surfacing as an unhandled traceback with no log record.

    The entrypoint owns logging (adr/0005); `config.py` is library code and
    only raises, so this is the layer that has to turn the raise into a
    record. ADR-shaped rather than a `job_runs` row, because no service was
    built and no database was reachable.
    """

    def raise_config_error():
        raise RuntimeError(
            "HUGINN_YC_ALGOLIA_API_KEY is not set. Copy .env.example to .env."
        )

    def unexpected_build_service(config):
        pytest.fail("build_service must not run when config loading failed")

    monkeypatch.setattr(main_module, "load_config", raise_config_error)
    monkeypatch.setattr(main_module, "build_service", unexpected_build_service)
    caplog.set_level(logging.ERROR)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    errors = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "HUGINN_YC_ALGOLIA_API_KEY is not set" in errors[0].getMessage()


def test_main_does_not_swallow_unexpected_load_config_errors(monkeypatch):
    """Only the config-lookup failure is handled. A programming error inside
    `load_config` still propagates, so widening the handler later cannot
    quietly turn a crash into a clean exit code.
    """

    def raise_unexpected_error():
        raise ValueError("not a config error")

    monkeypatch.setattr(main_module, "load_config", raise_unexpected_error)

    with pytest.raises(ValueError, match="not a config error"):
        main()
