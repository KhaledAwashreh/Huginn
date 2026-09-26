"""Live-Postgres integration coverage for the statements
`PostgresCompanyRepository` runs against gold.company: the
`read_unenriched_company_names` read, the `read_domain_normalized_signals`
read, and the `upsert_company` write.

Runs against the throwaway Postgres that tests/conftest.py provisions,
skipped when testcontainers or Docker is unavailable. The fake-repository
unit tests elsewhere (e.g. test_company.py) can't verify real SQL execution
against gold.company (column names, the `business_sector IS NULL` filter,
`created_at` ordering, the `LIMIT` bind, and which of the two write shapes
`build_upsert_query` picks); this is that verification. See
architecture-notes/opencorporates-fetch-plan.md section 5.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from huginn.elt.gold.repositories.company_repository import PostgresCompanyRepository

# read_unenriched_company_names returns the *oldest* unenriched rows up to
# the caller's limit, so a fixture inserted at now() only appears in the
# result while the table happens to hold fewer unenriched rows than the
# limit. The table is shared for the whole session, so a fixture that
# happened to sort late could fall outside the window. Pinning created_at to
# the epoch makes each fixture the oldest unenriched row by construction, so
# the assertions hold no matter what else the session has left behind.
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

_BEFORE_EPOCH = datetime(2000, 1, 1, tzinfo=UTC)
"""A current_since far enough in the past that any now() the writer writes
is unambiguously greater, so a test can assert whether current_since moved
without comparing against a Python-side clock."""


def _insert_company(
    cur,
    domain: str,
    name: str,
    business_sector: list[str] | None,
    created_at: datetime,
    current_since: datetime | None = None,
    eu_startups_searched_at: datetime | None = None,
) -> None:
    """Insert one isolated company fixture through the supplied cursor.

    `current_since` left None keeps the column default, which is what the
    read_unenriched_company_names tests below want; pinning it is how the
    write tests tell a bumped current_since from an untouched one.
    `eu_startups_searched_at` is the ADR-0010 candidate gate's marker: NULL
    still means the company is awaiting an EU-Startups search, so the
    fixture default of None is the pending case.
    """
    cur.execute(
        """
        INSERT INTO gold.company
            (domain, name, business_sector, created_at, current_since,
             eu_startups_searched_at)
        VALUES (%s, %s, %s, %s, COALESCE(%s, now()), %s)
        """,
        (
            domain,
            name,
            business_sector,
            created_at,
            current_since,
            eu_startups_searched_at,
        ),
    )


def _stored_company(cur, domain: str) -> dict:
    """Read one gold.company row back by column name."""
    cur.execute("SELECT * FROM gold.company WHERE domain = %s", (domain,))
    row = cur.fetchone()
    if row is None:
        return {}
    return dict(zip([column.name for column in cur.description], row, strict=True))


def test_a_type_2_only_write_updates_an_existing_row_and_keeps_its_name(
    integration_database_url: str,
):
    """Regression, ADR-0013. `name` is NOT NULL and, unlike `domain`, was
    not hardcoded into the INSERT column list, so
    a write carrying only a Type 2 field built an INSERT missing `name` and
    Postgres rejected it with NotNullViolation before ON CONFLICT was
    considered, even though the row existed and only the update branch
    should have run. The whole `write_all` transaction aborted. This is the
    shape a KAN-43 enrichment writer calls, and the shape
    test_company_repository.py already advertised while asserting only on
    SQL text.
    """
    domain = f"type2only-{str(uuid.uuid4().int)[:10]}.example"

    try:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            _insert_company(
                cur, domain, "Original Name", ["fintech"], _EPOCH, _BEFORE_EPOCH
            )

        with PostgresCompanyRepository(integration_database_url) as repository:
            repository.upsert_company(
                domain,
                {"business_sector": ["b2b", "fintech"]},
                bump_current_since=True,
            )

        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            stored = _stored_company(cur, domain)

        assert stored["business_sector"] == ["b2b", "fintech"]
        assert stored["name"] == "Original Name"
        assert stored["current_since"] > _BEFORE_EPOCH
    finally:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM gold.company WHERE domain = %s", (domain,))


def test_a_type_2_only_write_against_an_unknown_domain_writes_nothing_and_raises(
    integration_database_url: str,
):
    """A write with no `name` has nothing to insert, so the insert branch
    must not run: binding the domain, a placeholder, or the empty string
    would put a fabricated value into the column the lead digest shows as
    the company's name. Doing nothing silently is the other wrong answer,
    since `write_company` counts the domain as written either way, so a
    name-less write against no row is an error the caller has to see.
    """
    domain = f"type2only-absent-{str(uuid.uuid4().int)[:10]}.example"

    with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
        assert _stored_company(cur, domain) == {}

    with (
        PostgresCompanyRepository(integration_database_url) as repository,
        pytest.raises(ValueError, match=domain),
    ):
        repository.upsert_company(
            domain, {"business_sector": ["fintech"]}, bump_current_since=False
        )

    with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
        assert _stored_company(cur, domain) == {}


def test_a_name_bearing_write_inserts_then_updates_the_same_row(
    integration_database_url: str,
):
    """The shape `CompanyWriter.write_all` produces today, and the one the
    statement is built for when `name` is present. Still a single
    `INSERT ... ON CONFLICT`: one row, not two, and the second write
    updates it in place.
    """
    domain = f"upsert-{str(uuid.uuid4().int)[:10]}.example"

    try:
        with PostgresCompanyRepository(integration_database_url) as repository:
            repository.upsert_company(domain, {"name": "First Name"}, False)
        with PostgresCompanyRepository(integration_database_url) as repository:
            repository.upsert_company(
                domain,
                {"name": "Second Name", "company_scale": "11-100"},
                False,
            )

        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT count(*), min(name), min(company_scale) "
                "FROM gold.company WHERE domain = %s",
                (domain,),
            )
            (rows, name, company_scale) = cur.fetchone()

        assert rows == 1
        assert name == "Second Name"
        assert company_scale == "11-100"
    finally:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM gold.company WHERE domain = %s", (domain,))


def test_current_since_moves_on_an_update_only_when_the_write_asks_for_it(
    integration_database_url: str,
):
    """`bump_current_since` is the caller's statement that a Type 2 tracked
    field actually changed (ADR-0002), so it must move `current_since` on
    the write it is passed to and leave it alone otherwise. Both shapes of
    the write take the flag.
    """
    domain = f"bump-{str(uuid.uuid4().int)[:10]}.example"
    quiet_domain = f"bump-quiet-{str(uuid.uuid4().int)[:10]}.example"

    try:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            _insert_company(cur, domain, "Bumped", None, _EPOCH, _BEFORE_EPOCH)
            _insert_company(cur, quiet_domain, "Quiet", None, _EPOCH, _BEFORE_EPOCH)

        with PostgresCompanyRepository(integration_database_url) as repository:
            repository.upsert_company(
                domain, {"business_sector": ["fintech"]}, bump_current_since=True
            )
        with PostgresCompanyRepository(integration_database_url) as repository:
            repository.upsert_company(
                quiet_domain, {"company_status": "Active"}, bump_current_since=False
            )

        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            bumped = _stored_company(cur, domain)["current_since"]
            quiet = _stored_company(cur, quiet_domain)["current_since"]

        assert bumped > _BEFORE_EPOCH
        assert quiet == _BEFORE_EPOCH
    finally:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM gold.company WHERE domain IN (%s, %s)",
                (domain, quiet_domain),
            )


def test_a_write_carrying_no_values_at_all_touches_only_updated_at(
    integration_database_url: str,
):
    """An empty `new_values` has no column to set, so the write is an
    UPDATE of `updated_at` alone, and it must not attempt an insert: with
    nothing but `domain` to bind, that used to be a guaranteed
    NotNullViolation aborting the caller's transaction. Pinned because the
    shape reads like a no-op rather than like the failure it was.
    """
    domain = f"empty-{str(uuid.uuid4().int)[:10]}.example"

    try:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            _insert_company(
                cur, domain, "Untouched", None, _BEFORE_EPOCH, _BEFORE_EPOCH
            )

        with PostgresCompanyRepository(integration_database_url) as repository:
            repository.upsert_company(domain, {}, bump_current_since=False)

        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            stored = _stored_company(cur, domain)

        assert stored["name"] == "Untouched"
        assert stored["current_since"] == _BEFORE_EPOCH
        assert stored["updated_at"] > _BEFORE_EPOCH
    finally:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM gold.company WHERE domain = %s", (domain,))


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


def test_read_company_names_pending_eu_startups_search_returns_only_rows_with_null_column(
    integration_database_url: str,
):
    """Candidate reads exclude companies that already have eu_startups_searched_at
    set.
    """
    suffix = str(uuid.uuid4().int)[:10]
    pending_domain = f"eustartuptest-pending-{suffix}.example"
    searched_domain = f"eustartuptest-searched-{suffix}.example"
    now = datetime.now(UTC)

    try:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            _insert_company(
                cur,
                pending_domain,
                "PendingCo",
                ["software"],
                now,
                eu_startups_searched_at=None,
            )
            _insert_company(
                cur,
                searched_domain,
                "SearchedCo",
                ["software"],
                now,
                eu_startups_searched_at=now,
            )

        with PostgresCompanyRepository(integration_database_url) as repository:
            names = repository.read_company_names_pending_eu_startups_search(limit=1000)

        assert "PendingCo" in names
        assert "SearchedCo" not in names
    finally:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM gold.company WHERE domain IN (%s, %s)",
                (pending_domain, searched_domain),
            )
