"""Live-Postgres integration coverage for YcStagingLoader.load().

Runs against the throwaway Postgres that tests/conftest.py provisions,
fails rather than skips when testcontainers or Docker is unavailable (tests/conftest.py explains why).
"""

from __future__ import annotations

import uuid

import psycopg

from huginn.elt.silver.repositories.signal_resolution_repository import (
    PostgresSignalResolutionRepository,
)
from huginn.elt.silver.repositories.yc_staging_repository import (
    PostgresYcStagingRepository,
)
from huginn.elt.silver.signal_resolution import SignalResolver
from huginn.elt.silver.yc_staging import YcStagingLoader


def test_load_upserts_bronze_yc_hits_into_silver_yc_listings(
    integration_database_url: str,
):
    stable_id = str(uuid.uuid4().int)[:10]
    run_id = str(uuid.uuid4())
    with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO bronze.api_ingest (source, stable_id, payload, content_hash, run_id)
            VALUES ('yc', %s, %s, 'test-hash', %s::uuid)
            """,
            (
                stable_id,
                psycopg.types.json.Jsonb(
                    {
                        "id": int(stable_id),
                        "name": "IntegrationTestCo",
                        "slug": "integrationtestco",
                        "stage": "Early",
                        "website": "https://integrationtestco.example",
                        "isHiring": True,
                        "one_liner": "A test listing.",
                        "long_description": None,
                        "launched_at": 1700000000,
                    }
                ),
                run_id,
            ),
        )

    try:
        loader = YcStagingLoader(PostgresYcStagingRepository(integration_database_url))
        written = loader.load()

        assert written >= 1

        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT company_name_raw, description FROM silver.yc_listings WHERE stable_id = %s",
                (stable_id,),
            )
            company_name_raw, description = cur.fetchone()

        assert company_name_raw == "IntegrationTestCo"
        assert description == "A test listing."

        loader.load()
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM silver.yc_listings WHERE stable_id = %s",
                (stable_id,),
            )
            assert cur.fetchone()[0] == 1
    finally:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM silver.yc_listings WHERE stable_id = %s", (stable_id,)
            )
            cur.execute(
                "DELETE FROM bronze.api_ingest WHERE source = 'yc' AND stable_id = %s",
                (stable_id,),
            )


def _seed_bronze_yc_hit(database_url: str, stable_id: str, payload: dict) -> None:
    """Insert one bronze.api_ingest row the staging loader will pick up."""
    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO bronze.api_ingest (source, stable_id, payload, content_hash, run_id)
            VALUES ('yc', %s, %s, 'test-hash', %s::uuid)
            """,
            (
                stable_id,
                psycopg.types.json.Jsonb(payload),
                str(uuid.uuid4()),
            ),
        )


def _read_yc_profile_fields(
    database_url: str, stable_id: str
) -> tuple[str | None, int | None]:
    """Read the two YC-only profile columns straight out of silver."""
    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT company_status, team_size FROM silver.yc_listings "
            "WHERE stable_id = %s",
            (stable_id,),
        )
        return cur.fetchone()


def _read_yc_sector_and_location(
    database_url: str, stable_id: str
) -> tuple[list[str] | None, str | None]:
    """Read the industries array and the raw location string out of silver."""
    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT industries, all_locations FROM silver.yc_listings "
            "WHERE stable_id = %s",
            (stable_id,),
        )
        return cur.fetchone()


def test_load_persists_company_status_and_team_size(
    integration_database_url: str,
):
    """Round-trip the two YC-only columns through parse, upsert, and read.

    The unit tests prove the parser reads them and the resolver carries them.
    Only a real round-trip proves the columns are named the same way in the
    INSERT, the ON CONFLICT DO UPDATE, and the table.
    """
    stable_id = str(uuid.uuid4().int)[:10]
    payload = {
        "id": int(stable_id),
        "name": "ProfileFieldCo",
        "slug": "profilefieldco",
        "stage": "Growth",
        "status": "Public",
        "team_size": 50,
        "website": "https://profilefieldco.example",
        "isHiring": True,
        "one_liner": "A listing with profile fields.",
        "long_description": None,
        "launched_at": 1700000000,
    }

    try:
        _seed_bronze_yc_hit(integration_database_url, stable_id, payload)
        YcStagingLoader(PostgresYcStagingRepository(integration_database_url)).load()

        assert _read_yc_profile_fields(integration_database_url, stable_id) == (
            "Public",
            50,
        )
    finally:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM silver.yc_listings WHERE stable_id = %s", (stable_id,)
            )
            cur.execute(
                "DELETE FROM bronze.api_ingest WHERE source = 'yc' AND stable_id = %s",
                (stable_id,),
            )


def test_load_updates_profile_fields_on_conflict_rather_than_keeping_the_first(
    integration_database_url: str,
):
    """A re-run must overwrite the profile fields, not pin their first value.

    This is what a missed column in ON CONFLICT DO UPDATE SET looks like
    from outside: the row exists and is non-NULL, so nothing looks broken,
    it is just frozen at whatever the first ingest happened to say.
    """
    stable_id = str(uuid.uuid4().int)[:10]
    payload = {
        "id": int(stable_id),
        "name": "ProfileDriftCo",
        "slug": "profiledriftco",
        "stage": "Growth",
        "status": "Active",
        "team_size": 12,
        "website": "https://profiledriftco.example",
        "isHiring": True,
        "one_liner": "First ingest.",
        "long_description": None,
        "launched_at": 1700000000,
    }

    try:
        _seed_bronze_yc_hit(integration_database_url, stable_id, payload)
        loader = YcStagingLoader(PostgresYcStagingRepository(integration_database_url))
        loader.load()
        assert _read_yc_profile_fields(integration_database_url, stable_id) == (
            "Active",
            12,
        )

        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE bronze.api_ingest SET payload = %s "
                "WHERE source = 'yc' AND stable_id = %s",
                (
                    psycopg.types.json.Jsonb(
                        # "Public", not "Acquired": an acquired company is
                        # excluded by the parser, so a status change to it
                        # would skip the row entirely and this test would
                        # pass for the wrong reason. The status drift has to
                        # stay inside the set of statuses that get written.
                        {**payload, "status": "Public", "team_size": 640}
                    ),
                    stable_id,
                ),
            )

        loader.load()

        assert _read_yc_profile_fields(integration_database_url, stable_id) == (
            "Public",
            640,
        )
    finally:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM silver.yc_listings WHERE stable_id = %s", (stable_id,)
            )
            cur.execute(
                "DELETE FROM bronze.api_ingest WHERE source = 'yc' AND stable_id = %s",
                (stable_id,),
            )


def test_load_persists_a_zero_headcount_rather_than_storing_null(
    integration_database_url: str,
):
    """A reported 0 must land in the INTEGER column as 0.

    Losing the distinction here is invisible downstream: Gold sees NULL for
    both a zero and an unknown, so the company drops out of the lowest band
    instead of being counted in it.
    """
    stable_id = str(uuid.uuid4().int)[:10]
    payload = {
        "id": int(stable_id),
        "name": "PreHireCo",
        "slug": "prehireco",
        "stage": "Early",
        "status": "Active",
        "team_size": 0,
        "website": "https://prehireco.example",
        "isHiring": True,
        "one_liner": "Before the first hire.",
        "long_description": None,
        "launched_at": 1700000000,
    }

    try:
        _seed_bronze_yc_hit(integration_database_url, stable_id, payload)
        YcStagingLoader(PostgresYcStagingRepository(integration_database_url)).load()

        assert _read_yc_profile_fields(integration_database_url, stable_id) == (
            "Active",
            0,
        )
    finally:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM silver.yc_listings WHERE stable_id = %s", (stable_id,)
            )
            cur.execute(
                "DELETE FROM bronze.api_ingest WHERE source = 'yc' AND stable_id = %s",
                (stable_id,),
            )


def test_load_persists_a_multi_valued_industries_array(
    integration_database_url: str,
):
    """The array must survive as an array, in order.

    A single round-trip is the only thing that catches the column being
    declared TEXT instead of TEXT[], which would store the list's repr and
    fail here rather than at Gold read time.
    """
    stable_id = str(uuid.uuid4().int)[:10]
    payload = {
        "id": int(stable_id),
        "name": "MultiSectorCo",
        "slug": "multisectorco",
        "stage": "Growth",
        "status": "Active",
        "team_size": 30,
        "industries": ["B2B", "Fintech", "HealthCare"],
        "all_locations": "Berlin, Germany; Remote",
        "website": "https://multisectorco.example",
        "isHiring": True,
        "one_liner": "Several sectors at once.",
        "long_description": None,
        "launched_at": 1700000000,
    }

    try:
        _seed_bronze_yc_hit(integration_database_url, stable_id, payload)
        YcStagingLoader(PostgresYcStagingRepository(integration_database_url)).load()

        assert _read_yc_sector_and_location(integration_database_url, stable_id) == (
            ["B2B", "Fintech", "HealthCare"],
            "Berlin, Germany; Remote",
        )
    finally:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM silver.yc_listings WHERE stable_id = %s", (stable_id,)
            )
            cur.execute(
                "DELETE FROM bronze.api_ingest WHERE source = 'yc' AND stable_id = %s",
                (stable_id,),
            )


def test_load_stores_absent_industries_as_null_not_an_empty_array(
    integration_database_url: str,
):
    """NULL and '{}' mean different things and only one of them is right.

    An empty array would reach Gold as a real value, so a later run that
    learns the industries would look like a change of sector rather than the
    first time the sector was known.
    """
    stable_id = str(uuid.uuid4().int)[:10]
    payload = {
        "id": int(stable_id),
        "name": "NoSectorCo",
        "slug": "nosectorco",
        "stage": "Early",
        "status": "Active",
        "website": "https://nosectorco.example",
        "isHiring": True,
        "one_liner": "No industries key at all.",
        "long_description": None,
        "launched_at": 1700000000,
    }

    try:
        _seed_bronze_yc_hit(integration_database_url, stable_id, payload)
        YcStagingLoader(PostgresYcStagingRepository(integration_database_url)).load()

        industries, _ = _read_yc_sector_and_location(
            integration_database_url, stable_id
        )
        assert industries is None
    finally:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM silver.yc_listings WHERE stable_id = %s", (stable_id,)
            )
            cur.execute(
                "DELETE FROM bronze.api_ingest WHERE source = 'yc' AND stable_id = %s",
                (stable_id,),
            )


def test_load_stores_an_explicitly_empty_industries_array_as_empty_not_null(
    integration_database_url: str,
):
    """The other half of the NULL-versus-empty rule the absent-key test covers.

    A key present with an empty list is the source reporting no industries,
    which is a real value. The parameter builder distinguishes the two with
    `if row.industries is not None`; loosening that to a truthiness check
    would write SQL NULL here, and every other test in the suite would still
    pass, because none of them seeds an explicitly empty array.
    """
    stable_id = str(uuid.uuid4().int)[:10]
    payload = {
        "id": int(stable_id),
        "name": "EmptySectorCo",
        "slug": "emptysectorco",
        "stage": "Early",
        "status": "Active",
        "industries": [],
        "former_names": [],
        "website": "https://emptysectorco.example",
        "isHiring": True,
        "one_liner": "Reports no industries at all.",
        "long_description": None,
        "launched_at": 1700000000,
    }

    try:
        _seed_bronze_yc_hit(integration_database_url, stable_id, payload)
        YcStagingLoader(PostgresYcStagingRepository(integration_database_url)).load()

        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT industries, former_names FROM silver.yc_listings "
                "WHERE stable_id = %s",
                (stable_id,),
            )
            industries, former_names = cur.fetchone()
        assert industries == []
        assert former_names == []
    finally:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM silver.yc_listings WHERE stable_id = %s", (stable_id,)
            )
            cur.execute(
                "DELETE FROM bronze.api_ingest WHERE source = 'yc' AND stable_id = %s",
                (stable_id,),
            )


def test_former_names_survive_the_whole_silver_path(
    integration_database_url: str,
):
    """former_names end to end, which nothing pinned before.

    The field is read by no current logic (KAN-4 owns the matcher), so a
    copy dropped in either the staging upsert or the resolver would leave
    the whole suite green. That is the exact hazard of capturing a field
    ahead of its consumer.
    """
    stable_id = str(uuid.uuid4().int)[:10]
    payload = {
        "id": int(stable_id),
        "name": "FormerNamesCo",
        "slug": "formernamesco",
        "stage": "Growth",
        "status": "Active",
        "team_size": 12,
        "former_names": ["ZenPayroll", "Zen Payroll", "formernamesco"],
        "website": "https://formernamesco.example",
        "isHiring": True,
        "one_liner": "Was called something else.",
        "long_description": None,
        "launched_at": 1700000000,
    }

    try:
        _seed_bronze_yc_hit(integration_database_url, stable_id, payload)
        YcStagingLoader(PostgresYcStagingRepository(integration_database_url)).load()
        SignalResolver(
            PostgresSignalResolutionRepository(integration_database_url)
        ).resolve_all()

        expected = ["ZenPayroll", "Zen Payroll", "formernamesco"]
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT former_names FROM silver.yc_listings WHERE stable_id = %s",
                (stable_id,),
            )
            assert cur.fetchone() == (expected,)
            cur.execute(
                "SELECT former_names FROM silver.resolved_signals "
                "WHERE source = 'yc' AND source_stable_id = %s",
                (stable_id,),
            )
            assert cur.fetchone() == (expected,)
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
            cur.execute(
                "DELETE FROM silver.yc_listings WHERE stable_id = %s", (stable_id,)
            )
            cur.execute(
                "DELETE FROM bronze.api_ingest WHERE source = 'yc' AND stable_id = %s",
                (stable_id,),
            )


def test_load_updates_industries_on_conflict(
    integration_database_url: str,
):
    """Same reason as the status/headcount drift test: a column left out of
    ON CONFLICT DO UPDATE SET looks perfectly fine and stays frozen at
    whatever the first ingest said.
    """
    stable_id = str(uuid.uuid4().int)[:10]
    payload = {
        "id": int(stable_id),
        "name": "SectorDriftCo",
        "slug": "sectordriftco",
        "stage": "Growth",
        "status": "Active",
        "team_size": 30,
        "industries": ["Fintech"],
        "all_locations": "Austin, TX, USA",
        "website": "https://sectordriftco.example",
        "isHiring": True,
        "one_liner": "First ingest.",
        "long_description": None,
        "launched_at": 1700000000,
    }

    try:
        _seed_bronze_yc_hit(integration_database_url, stable_id, payload)
        loader = YcStagingLoader(PostgresYcStagingRepository(integration_database_url))
        loader.load()
        assert _read_yc_sector_and_location(integration_database_url, stable_id) == (
            ["Fintech"],
            "Austin, TX, USA",
        )

        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE bronze.api_ingest SET payload = %s "
                "WHERE source = 'yc' AND stable_id = %s",
                (
                    psycopg.types.json.Jsonb(
                        {
                            **payload,
                            "industries": ["B2B", "Fintech"],
                            "all_locations": "Denver, CO, USA; Remote",
                        }
                    ),
                    stable_id,
                ),
            )

        loader.load()

        assert _read_yc_sector_and_location(integration_database_url, stable_id) == (
            ["B2B", "Fintech"],
            "Denver, CO, USA; Remote",
        )
    finally:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM silver.yc_listings WHERE stable_id = %s", (stable_id,)
            )
            cur.execute(
                "DELETE FROM bronze.api_ingest WHERE source = 'yc' AND stable_id = %s",
                (stable_id,),
            )


def test_load_never_writes_an_acquired_or_inactive_company_to_silver(
    integration_database_url: str,
):
    """End-to-end through the real loader, because the parser returning None
    and the loader honouring it are two separate things and only the second
    one keeps the row out of the table.
    """
    kept = str(uuid.uuid4().int)[:10]
    acquired = str(uuid.uuid4().int)[:10]
    inactive = str(uuid.uuid4().int)[:10]
    base = {
        "stage": "Growth",
        "team_size": 20,
        "website": "https://exclco.example",
        "isHiring": True,
        "one_liner": "Should not be staged.",
        "long_description": None,
        "launched_at": 1700000000,
    }
    payloads = {
        kept: {
            **base,
            "id": int(kept),
            "name": "KeptCo",
            "slug": "keptco",
            "status": "Active",
        },
        acquired: {
            **base,
            "id": int(acquired),
            "name": "AcquiredCo",
            "slug": "acquiredco",
            "status": "Acquired",
        },
        inactive: {
            **base,
            "id": int(inactive),
            "name": "InactiveCo",
            "slug": "inactiveco",
            "status": "Inactive",
        },
    }

    try:
        for stable_id, payload in payloads.items():
            _seed_bronze_yc_hit(integration_database_url, stable_id, payload)
        YcStagingLoader(PostgresYcStagingRepository(integration_database_url)).load()

        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT stable_id FROM silver.yc_listings WHERE stable_id = ANY(%s)",
                ([kept, acquired, inactive],),
            )
            assert [r[0] for r in cur.fetchall()] == [kept]
    finally:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM silver.yc_listings WHERE stable_id = ANY(%s)",
                ([kept, acquired, inactive],),
            )
            cur.execute(
                "DELETE FROM bronze.api_ingest WHERE source = 'yc' "
                "AND stable_id = ANY(%s)",
                ([kept, acquired, inactive],),
            )


def test_batch_travels_bronze_to_yc_listings_to_resolved_signals(
    integration_database_url: str,
):
    """The whole Silver path for the batch label, in one test.

    Three separate column lists have to agree on the name: the yc_listings
    INSERT, the yc_listings SELECT the resolver reads, and the
    resolved_signals INSERT. A mismatch in any one of them fails silently
    rather than loudly, because the resolver's row-index mapping is
    positional, so a column inserted in the SELECT at the wrong offset
    lands a neighbouring column's value in `batch`.
    """
    stable_id = str(uuid.uuid4().int)[:10]
    payload = {
        "id": int(stable_id),
        "name": "BatchPathCo",
        "slug": "batchpathco",
        "stage": "Growth",
        "status": "Active",
        "team_size": 20,
        "industries": ["Fintech"],
        "all_locations": "Austin, TX, USA",
        "batch": "Winter 2022",
        "website": "https://batchpathco.example",
        "isHiring": True,
        "one_liner": "Carries a batch end to end.",
        "long_description": None,
        "launched_at": 1700000000,
    }

    try:
        _seed_bronze_yc_hit(integration_database_url, stable_id, payload)
        YcStagingLoader(PostgresYcStagingRepository(integration_database_url)).load()
        SignalResolver(
            PostgresSignalResolutionRepository(integration_database_url)
        ).resolve_all()

        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT batch FROM silver.yc_listings WHERE stable_id = %s",
                (stable_id,),
            )
            assert cur.fetchone() == ("Winter 2022",)
            cur.execute(
                "SELECT batch FROM silver.resolved_signals "
                "WHERE source = 'yc' AND source_stable_id = %s",
                (stable_id,),
            )
            assert cur.fetchone() == ("Winter 2022",)
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
            cur.execute(
                "DELETE FROM silver.yc_listings WHERE stable_id = %s", (stable_id,)
            )
            cur.execute(
                "DELETE FROM bronze.api_ingest WHERE source = 'yc' AND stable_id = %s",
                (stable_id,),
            )
