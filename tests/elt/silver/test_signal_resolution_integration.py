"""Live-Postgres integration coverage for SignalResolver.

Runs against the throwaway Postgres that tests/conftest.py provisions,
skipped when testcontainers or Docker is unavailable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import psycopg

from huginn.elt.silver.repositories.signal_resolution_repository import (
    PostgresSignalResolutionRepository,
)
from huginn.elt.silver.signal_resolution import SignalResolver

_YC_PROFILE_HIT = {
    "stage": "Growth",
    "status": "Acquired",
    "team_size": 640,
    "industries": ["B2B", "Fintech"],
    "all_locations": "Berlin, Germany; Remote",
    "website": "https://ycprofiletestco.example",
    "isHiring": False,
    "one_liner": "A resolved YC listing.",
    "long_description": None,
    "launched_at": 1700000000,
}


def _insert_hn_posting(cur, stable_id: str, website: str | None) -> None:
    cur.execute(
        """
        INSERT INTO silver.hn_postings
            (stable_id, company_name_raw, website, signal_type, occurred_on, url)
        VALUES (%s, %s, %s, 'hiring', %s, %s)
        """,
        (
            stable_id,
            "ResolutionTestCo",
            website,
            datetime.now(UTC),
            "https://example.invalid",
        ),
    )


def test_resolve_all_auto_matches_a_row_with_a_website(
    integration_database_url: str,
):
    """Persist a normalized domain key for a row with a company website."""
    stable_id = str(uuid.uuid4().int)[:10]
    with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
        _insert_hn_posting(cur, stable_id, "https://www.resolutiontestco.example")

    try:
        resolver = SignalResolver(
            PostgresSignalResolutionRepository(integration_database_url)
        )
        written = resolver.resolve_all()

        assert written >= 1

        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT resolved_company_key, key_derivation FROM silver.resolved_signals "
                "WHERE source = 'hn' AND source_stable_id = %s",
                (stable_id,),
            )
            key, confidence = cur.fetchone()

        assert key == "resolutiontestco.example"
        assert confidence == "domain_normalized"
    finally:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM silver.resolved_signals WHERE source = 'hn' AND source_stable_id = %s",
                (stable_id,),
            )
            cur.execute(
                "DELETE FROM silver.hn_postings WHERE stable_id = %s", (stable_id,)
            )


def test_resolve_all_marks_unresolved_when_website_is_none(
    integration_database_url: str,
):
    """Persist an unresolved derivation status when the website is absent."""
    stable_id = str(uuid.uuid4().int)[:10]
    with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
        _insert_hn_posting(cur, stable_id, None)

    try:
        SignalResolver(
            PostgresSignalResolutionRepository(integration_database_url)
        ).resolve_all()

        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT resolved_company_key, key_derivation FROM silver.resolved_signals "
                "WHERE source = 'hn' AND source_stable_id = %s",
                (stable_id,),
            )
            key, confidence = cur.fetchone()

        assert key == f"unresolved:hn:{stable_id}"
        assert confidence == "unresolved"
    finally:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM silver.resolved_signals WHERE source = 'hn' AND source_stable_id = %s",
                (stable_id,),
            )
            cur.execute(
                "DELETE FROM silver.hn_postings WHERE stable_id = %s", (stable_id,)
            )


def test_resolve_all_persists_yc_profile_fields_onto_the_shared_table(
    integration_database_url: str,
):
    """The two YC-only columns must land on silver.resolved_signals.

    resolved_signals is cross-source but still event grain, so it carries
    every staging column including the ones only one source supplies. Gold
    reads status and headcount from here and nowhere else, so a drop at this
    step empties gold.company.company_status for every YC company.
    """
    stable_id = str(uuid.uuid4().int)[:10]
    with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO silver.yc_listings
                (stable_id, company_name_raw, website, signal_type, stage,
                 company_status, team_size, industries, all_locations,
                 description, occurred_on, url)
            VALUES (%s, 'YcProfileTestCo', %s, 'program_milestone', %s, %s, %s,
                    %s, %s, %s, %s, 'https://example.invalid')
            """,
            (
                stable_id,
                _YC_PROFILE_HIT["website"],
                _YC_PROFILE_HIT["stage"],
                _YC_PROFILE_HIT["status"],
                _YC_PROFILE_HIT["team_size"],
                _YC_PROFILE_HIT["industries"],
                _YC_PROFILE_HIT["all_locations"],
                _YC_PROFILE_HIT["one_liner"],
                datetime.now(UTC),
            ),
        )

    try:
        SignalResolver(
            PostgresSignalResolutionRepository(integration_database_url)
        ).resolve_all()

        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT resolved_company_key, company_status, team_size, "
                "industries, all_locations "
                "FROM silver.resolved_signals "
                "WHERE source = 'yc' AND source_stable_id = %s",
                (stable_id,),
            )
            key, company_status, team_size, industries, all_locations = cur.fetchone()

        assert key == "ycprofiletestco.example"
        assert company_status == "Acquired"
        assert team_size == 640
        assert industries == ["B2B", "Fintech"]
        assert all_locations == "Berlin, Germany; Remote"
    finally:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM silver.resolved_signals WHERE source = 'yc' AND source_stable_id = %s",
                (stable_id,),
            )
            cur.execute(
                "DELETE FROM silver.yc_listings WHERE stable_id = %s", (stable_id,)
            )


def test_resolved_signals_leaves_profile_fields_null_for_hn_rows(
    integration_database_url: str,
):
    """HN has neither field, so the shared table must hold NULL, not a default.

    A non-NULL value here would mean the resolution upsert is writing
    another source's value onto an HN row, which is a merge bug rather than
    a missing-data one and would be much harder to spot downstream.
    """
    stable_id = str(uuid.uuid4().int)[:10]
    with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
        _insert_hn_posting(cur, stable_id, "https://www.hnnulltestco.example")

    try:
        SignalResolver(
            PostgresSignalResolutionRepository(integration_database_url)
        ).resolve_all()

        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT company_status, team_size, industries, all_locations "
                "FROM silver.resolved_signals "
                "WHERE source = 'hn' AND source_stable_id = %s",
                (stable_id,),
            )
            company_status, team_size, industries, all_locations = cur.fetchone()

        assert company_status is None
        assert team_size is None
        assert industries is None
        assert all_locations is None
    finally:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM silver.resolved_signals WHERE source = 'hn' AND source_stable_id = %s",
                (stable_id,),
            )
            cur.execute(
                "DELETE FROM silver.hn_postings WHERE stable_id = %s", (stable_id,)
            )
