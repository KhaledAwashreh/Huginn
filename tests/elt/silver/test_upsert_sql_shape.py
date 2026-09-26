"""Column-list and placeholder parity for the hand-written Silver upserts.

These SQL statements are plain string constants, so nothing but a test stops
the column list and the VALUES list from drifting apart when a column is
added. Both times a source field was added to these upserts during the
industries/all_locations/former_names work, the column list gained an entry
and the VALUES list did not, and the only symptom was
psycopg.ProgrammingError at runtime, on the first row of a real ingest
against the real database. That is an expensive way to find a typo.

A parity check needs no database at all, which is the point: the failure
mode this guards is only visible in an integration test, by which point it
is a live round-trip rather than a unit test.
"""

from __future__ import annotations

import re
from dataclasses import fields
from datetime import UTC, datetime

import pytest

from huginn.elt.silver.models import (
    ResolvedSignalRecord,
    YcListingStaging,
)
from huginn.elt.silver.repositories.signal_resolution_repository import (
    _UPSERT_SQL as RESOLVED_UPSERT_SQL,
)
from huginn.elt.silver.repositories.yc_staging_repository import (
    _UPSERT_SQL as STAGING_UPSERT_SQL,
)
from huginn.elt.silver.repositories.yc_staging_repository import (
    build_upsert_query,
)

_INSERT_COLUMNS = re.compile(
    r"INSERT INTO\s+\S+\s*\((?P<columns>[^)]*)\)", re.IGNORECASE
)
_VALUES = re.compile(r"VALUES\s*\((?P<placeholders>[^)]*)\)", re.IGNORECASE)

_CONFLICT_TARGETS = frozenset({"stable_id", "source", "source_stable_id"})
"""Columns the upsert keys on. They appear in the INSERT list but are
intentionally not reassigned in the ON CONFLICT SET list, so they are
excluded when the INSERT list is compared against a record's field names."""


def _column_count(sql: str) -> int:
    match = _INSERT_COLUMNS.search(sql)
    assert match is not None, f"no INSERT column list found in:\n{sql}"
    return len([c for c in match.group("columns").split(",") if c.strip()])


def _placeholder_count(sql: str) -> int:
    match = _VALUES.search(sql)
    assert match is not None, f"no VALUES list found in:\n{sql}"
    return match.group("placeholders").count("%s")


@pytest.mark.parametrize(
    "sql",
    [STAGING_UPSERT_SQL, RESOLVED_UPSERT_SQL],
    ids=["yc_listings", "resolved_signals"],
)
def test_insert_column_count_matches_the_values_placeholder_count(sql: str):
    assert _placeholder_count(sql) == _column_count(sql)


def test_upsert_sets_every_inserted_column_on_conflict():
    """A column in the INSERT list but missing from the DO UPDATE SET list
    writes once and then silently freezes at whatever the first ingest said,
    which for a re-run of the same source is a value that can only be wrong.
    """
    for sql in (STAGING_UPSERT_SQL, RESOLVED_UPSERT_SQL):
        update_set = sql.split("DO UPDATE", 1)[1]
        for column in _INSERT_COLUMNS.search(sql).group("columns").split(","):
            column = column.strip()
            # The conflict target itself is intentionally not reassigned.
            if column in _CONFLICT_TARGETS:
                continue
            assert f"{column} = EXCLUDED.{column}" in update_set, (
                f"{column} is inserted but never updated on conflict"
            )


def test_staging_builder_supplies_one_parameter_per_placeholder():
    _, params = build_upsert_query(
        YcListingStaging(
            stable_id="1",
            company_name_raw="Acme",
            website=None,
            signal_type="hiring",
            stage=None,
            occurred_on=datetime.now(UTC),
            description="",
            url="https://example.invalid",
        )
    )
    assert len(params) == _placeholder_count(STAGING_UPSERT_SQL)


def _record_field_names(record_type: type) -> set[str]:
    return {field.name for field in fields(record_type)}


def _insert_columns(sql: str) -> set[str]:
    return {c.strip() for c in _INSERT_COLUMNS.search(sql).group("columns").split(",")}


def test_upsert_binds_exactly_the_fields_the_record_declares():
    """A field on the record that the upsert forgets is the same drift as a
    missing placeholder, one layer up: the value parses, resolves, and then
    is silently dropped at the boundary, with every other test still green.

    The expected set is derived from each dataclass rather than restated, so
    adding a field to a record without adding it to the matching INSERT list
    fails here instead of being discovered against a live database. Every
    record field, including the ON CONFLICT target, is a real column.
    """
    assert _insert_columns(STAGING_UPSERT_SQL) == _record_field_names(YcListingStaging)
    assert _insert_columns(RESOLVED_UPSERT_SQL) == _record_field_names(
        ResolvedSignalRecord
    )


def test_resolved_record_exposes_every_field_the_upsert_binds():
    """Cheap tripwire: a new field on the record that the upsert forgets is
    the same drift as a missing placeholder, one layer up.
    """
    record = ResolvedSignalRecord(
        source_stable_id="1",
        source="yc",
        resolved_company_key="acme.example",
        company_name_raw="Acme",
        signal_type="hiring",
        stage=None,
        description="",
        occurred_on=datetime.now(UTC),
        url="https://example.invalid",
        key_derivation="domain_normalized",
    )
    bound = _record_field_names(ResolvedSignalRecord)
    assert bound == _insert_columns(RESOLVED_UPSERT_SQL)
    assert record.industries is None and record.former_names is None
