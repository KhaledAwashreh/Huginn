"""Live-Postgres integration coverage for
`PostgresCompanyRepository.read_unenriched_company_names`.

Runs against the throwaway Postgres that tests/conftest.py provisions,
skipped when testcontainers or Docker is unavailable. The fake-repository
unit tests elsewhere (e.g. test_company.py) can't verify real SQL execution
against gold.company (column names, the `business_sector IS NULL` filter,
`created_at` ordering, the `LIMIT` bind); this is that verification. See
architecture-notes/opencorporates-fetch-plan.md section 5.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import psycopg

from huginn.elt.gold.repositories.company_repository import PostgresCompanyRepository

# read_unenriched_company_names returns the *oldest* unenriched rows up to
# the caller's limit, so a fixture inserted at now() only appears in the
# result while the table happens to hold fewer unenriched rows than the
# limit. The table is shared for the whole session, so a fixture that
# happened to sort late could fall outside the window. Pinning created_at to
# the epoch makes each fixture the oldest unenriched row by construction, so
# the assertions hold no matter what else the session has left behind.
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _insert_company(
    cur, domain: str, name: str, business_sector: list[str] | None, created_at: datetime
) -> None:
    """Insert one isolated company fixture through the supplied cursor."""
    cur.execute(
        """
        INSERT INTO gold.company (domain, name, business_sector, created_at)
        VALUES (%s, %s, %s, %s)
        """,
        (domain, name, business_sector, created_at),
    )


def test_read_unenriched_company_names_returns_only_rows_with_null_business_sector(
    integration_database_url: str,
):
    """Candidate reads exclude companies that already have a sector."""
    suffix = str(uuid.uuid4().int)[:10]
    unenriched_domain = f"opencorptest-unenriched-{suffix}.example"
    enriched_domain = f"opencorptest-enriched-{suffix}.example"

    try:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            _insert_company(cur, unenriched_domain, "UnenrichedCo", None, _EPOCH)
            _insert_company(cur, enriched_domain, "EnrichedCo", ["software"], _EPOCH)

        with PostgresCompanyRepository(integration_database_url) as repository:
            names = repository.read_unenriched_company_names(limit=1000)

        assert "UnenrichedCo" in names
        assert "EnrichedCo" not in names
    finally:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM gold.company WHERE domain IN (%s, %s)",
                (unenriched_domain, enriched_domain),
            )


def test_read_unenriched_company_names_orders_oldest_created_first(
    integration_database_url: str,
):
    """Candidate reads prioritize the oldest company row."""
    suffix = str(uuid.uuid4().int)[:10]
    older_domain = f"opencorptest-older-{suffix}.example"
    newer_domain = f"opencorptest-newer-{suffix}.example"
    older = _EPOCH
    newer = _EPOCH + timedelta(seconds=1)

    try:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            # Insert newer row first so a correct ORDER BY, not insertion
            # order, is what the assertion below actually exercises.
            _insert_company(cur, newer_domain, "NewerCo", None, newer)
            _insert_company(cur, older_domain, "OlderCo", None, older)

        with PostgresCompanyRepository(integration_database_url) as repository:
            names = repository.read_unenriched_company_names(limit=1000)

        assert names.index("OlderCo") < names.index("NewerCo")
    finally:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM gold.company WHERE domain IN (%s, %s)",
                (older_domain, newer_domain),
            )


def test_read_unenriched_company_names_respects_the_limit(
    integration_database_url: str,
):
    """Candidate reads never exceed the caller's requested limit."""
    suffix = str(uuid.uuid4().int)[:10]
    domains = [f"opencorptest-limit-{suffix}-{i}.example" for i in range(3)]
    now = datetime.now(UTC)

    try:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            for i, domain in enumerate(domains):
                _insert_company(
                    cur, domain, f"LimitCo{i}", None, now + timedelta(seconds=i)
                )

        with PostgresCompanyRepository(integration_database_url) as repository:
            names = repository.read_unenriched_company_names(limit=2)

        assert len(names) <= 2
    finally:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM gold.company WHERE domain = ANY(%s)",
                (domains,),
            )


def test_read_domain_normalized_signals_maps_every_column_to_its_own_field(
    integration_database_url: str,
):
    """The read is positional (`row[0]`..`row[7]`), so a column reordered in
    the SELECT lands a neighbouring column's value in the wrong dataclass
    field with no error anywhere. Seeding one row whose every field holds a
    distinct, recognizable value is the only way to catch that: swapping
    `all_locations` and `batch`, or `country`-producing text with the batch
    label, would otherwise pass every other test and write garbage into
    gold.company.
    """
    suffix = str(uuid.uuid4().int)[:10]
    stable_id = f"goldmap{suffix}"
    domain = f"goldmaptest-{suffix}.example"

    try:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO silver.resolved_signals
                    (source_stable_id, source, resolved_company_key,
                     company_name_raw, signal_type, occurred_on, url,
                     key_derivation, stage, company_status, team_size,
                     industries, all_locations, batch)
                VALUES (%s, 'yc', %s, 'GoldMapCo', 'hiring', %s,
                        'https://example.invalid', 'domain_normalized',
                        'GrowthStageMarker', 'ActiveStatusMarker', 4321,
                        %s, 'LocationMarker City, Markerland', 'BatchMarker 2031')
                """,
                (
                    stable_id,
                    domain,
                    _EPOCH,
                    ["IndustryOneMarker", "IndustryTwoMarker"],
                ),
            )

        with PostgresCompanyRepository(integration_database_url) as repository:
            signals = repository.read_domain_normalized_signals()

        mine = [s for s in signals if s.domain == domain]
        assert len(mine) == 1
        signal = mine[0]
        assert signal.company_name_raw == "GoldMapCo"
        assert signal.stage == "GrowthStageMarker"
        assert signal.company_status == "ActiveStatusMarker"
        assert signal.team_size == 4321
        assert signal.industries == ["IndustryOneMarker", "IndustryTwoMarker"]
        assert signal.all_locations == "LocationMarker City, Markerland"
        assert signal.batch == "BatchMarker 2031"
    finally:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM silver.manual_review_queue WHERE resolved_signal_id IN "
                "(SELECT id FROM silver.resolved_signals "
                " WHERE source = 'yc' AND source_stable_id = %s)",
                (stable_id,),
            )
            cur.execute(
                "DELETE FROM silver.resolved_signals "
                "WHERE source = 'yc' AND source_stable_id = %s",
                (stable_id,),
            )
