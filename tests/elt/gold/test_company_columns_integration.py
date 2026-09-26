"""Coverage for the one invariant that can only be checked against the
database: every name Gold can bind into gold.company is a real column of the
real table, and the generated statement for the whole set of them executes.

Runs against the throwaway Postgres that tests/conftest.py provisions,
skipped when testcontainers or Docker is unavailable.
`tests/elt/gold/test_company.py` guards the writer against the repository's
`_COMPANY_COLUMNS` allowlist, but both sides of that comparison are code, so
a name wrong in db/schema/gold.sql and wrong in `_COMPANY_COLUMNS` the same
way passes it. That is the `yc_batch` to `notes` rename: the suite stayed
green and `write_all()` raised UndefinedColumn on the first real ingest.
Reading the catalog is what makes the comparison independent of both code
paths, and executing the full-width statement is what catches a name that
resolves in the catalog but not in the statement the writer actually runs.
"""

from __future__ import annotations

import uuid

import psycopg

from huginn.elt.gold.repositories.company_repository import (
    _COMPANY_COLUMNS,
    PostgresCompanyRepository,
)

# The real gold.company columns a caller never supplies a value for, and why.
# `id` and the three timestamps come from column defaults, `domain` is the
# upsert key rather than a value (it is always the explicit `domain`
# parameter), and `current_since` is moved by `bump_current_since` through
# now() rather than bound. `_COMPANY_COLUMNS` is therefore expected to be
# exactly gold.company minus these five; a column added to the schema and
# left out of the allowlist is a column no writer can ever set.
_REPOSITORY_MANAGED_COLUMNS = frozenset(
    {"id", "domain", "current_since", "created_at", "updated_at"}
)

# One distinct, recognizable value per allowlisted column, so a column
# swapped for a neighbour in the generated statement is visible rather than
# absorbed by a column that happens to accept it. The three CHECK
# constraints in db/schema/gold.sql decide the legal vocabulary, so
# company_scale and team_composition_signal use band and enum members
# rather than free text.
_ALL_COLUMN_VALUES: dict[str, object] = {
    "name": "ColumnSetCo",
    "stage": "Growth",
    "company_status": "Active",
    "business_sector": ["AlphaSector", "BetaSector"],
    "notes": "YC Winter 2031",
    "company_scale": "101-1000",
    "legal_form": "Private Limited Company",
    "country": "Markerland",
    "city": "Markertown",
    "address": "1 Marker Street",
    "phone_number": "+49 30 000000",
    "email": "hello@marker.example",
    "team_composition_signal": "likely_yes",
}


def _real_company_columns(cur) -> set[str]:
    """Every column the live gold.company table actually has."""
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'gold' AND table_name = 'company'"
    )
    return {row[0] for row in cur.fetchall()}


def test_every_allowlisted_company_column_exists_in_the_real_table(
    integration_database_url: str,
):
    """The direction that bites. A name in `_COMPANY_COLUMNS` that the table
    does not have is not a silent no-op: it reaches the generated statement
    and the whole write raises UndefinedColumn, aborting `write_all`'s
    transaction. This is what the `yc_batch` to `notes` rename was.
    """
    with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
        real_columns = _real_company_columns(cur)

    missing = sorted(set(_COMPANY_COLUMNS) - real_columns)

    assert not missing, (
        f"_COMPANY_COLUMNS names columns gold.company does not have: {missing}. "
        f"The table has {sorted(real_columns)}."
    )


def test_the_allowlist_is_exactly_the_columns_a_caller_may_set(
    integration_database_url: str,
):
    """The other direction. A schema column nobody can write is a column
    that silently keeps its default forever, which reads as working code
    rather than as a gap.
    """
    with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
        real_columns = _real_company_columns(cur)

    unsettable = real_columns - _REPOSITORY_MANAGED_COLUMNS

    assert set(_COMPANY_COLUMNS) == unsettable, (
        "gold.company's settable columns and _COMPANY_COLUMNS disagree: "
        f"only in the schema {sorted(unsettable - set(_COMPANY_COLUMNS))}, "
        f"only in the allowlist {sorted(set(_COMPANY_COLUMNS) - unsettable)}"
    )


def test_domain_and_name_are_the_only_not_null_columns_without_a_default(
    integration_database_url: str,
):
    """`build_upsert_query` picks its statement shape on whether "name" is
    in `new_values`, and that is only the right test for "can this write
    insert" while `name` is the sole NOT NULL column besides `domain` with
    no default to satisfy it. A migration adding a third one makes the
    shape decision incomplete, and no test here could see that.
    """
    with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'gold' AND table_name = 'company' "
            "AND is_nullable = 'NO' AND column_default IS NULL"
        )
        not_null_without_default = {row[0] for row in cur.fetchall()}

    assert not_null_without_default == {"domain", "name"}


def test_a_write_carrying_every_allowlisted_column_lands_every_value(
    integration_database_url: str,
):
    """Execute the generated statement at full width, once. Until this
    existed only `name` was ever written to a real gold.company, so eleven
    allowlisted column names had never resolved inside a real statement:
    a wrong spelling of any of them, or a CHECK constraint no unit test
    models, was invisible. The KAN-43 enrichment writer is the caller that
    will supply the six columns `CompanyWriter` cannot derive.
    """
    # Precondition, not the point of the test: if the allowlist grows, the
    # fixture has to grow with it or this quietly stops being full width.
    assert set(_ALL_COLUMN_VALUES) == set(_COMPANY_COLUMNS)
    domain = f"columnset-{str(uuid.uuid4().int)[:10]}.example"

    try:
        with PostgresCompanyRepository(integration_database_url) as repository:
            repository.upsert_company(
                domain, dict(_ALL_COLUMN_VALUES), bump_current_since=True
            )

        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM gold.company WHERE domain = %s", (domain,))
            row = cur.fetchone()
            stored = dict(
                zip([column.name for column in cur.description], row, strict=True)
            )

        for column, value in _ALL_COLUMN_VALUES.items():
            assert stored[column] == value, (
                f"gold.company.{column} is {stored[column]!r}, wrote {value!r}"
            )
    finally:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM gold.company WHERE domain = %s", (domain,))
