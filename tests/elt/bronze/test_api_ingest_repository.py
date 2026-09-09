"""Query-builder coverage for the bronze.api_ingest repository.

These assertions moved here with the SQL itself: `_LOOKUP_SQL`,
`_WRITE_SQL`, `_TOUCH_SQL` and their builders now live in
huginn.elt.bronze.repositories.api_ingest_repository, not in
api_ingest_store.py. What they check is unchanged: parameterized SQL
only, never string-built (BEST_PRACTICES.md section 8.1).
"""

from psycopg.types.json import Jsonb

from huginn.elt.bronze.repositories.api_ingest_repository import (
    build_lookup_query,
    build_touch_query,
    build_write_query,
)


def test_build_lookup_query_is_parameterized_and_scoped_to_source_and_stable_id():
    sql, params = build_lookup_query("hn", "49522897")

    assert "hn" not in sql
    assert "49522897" not in sql
    assert params == ("hn", "49522897")
    assert "content_hash" in sql
    assert "bronze.api_ingest" in sql


def test_build_write_query_is_parameterized_with_jsonb_payload_and_uuid_cast_run_id():
    payload = {"id": 1, "title": "Backend Engineer"}
    sql, params = build_write_query("hn", "49522897", payload, "hash123", "run-uuid-1")

    assert "hn" not in sql
    assert "49522897" not in sql
    assert "hash123" not in sql
    assert "run-uuid-1" not in sql
    assert "ON CONFLICT" in sql
    assert "%s::uuid" in sql
    assert params[0] == "hn"
    assert params[1] == "49522897"
    assert isinstance(params[2], Jsonb)
    assert params[2].obj == payload
    assert params[3] == "hash123"
    assert params[4] == "run-uuid-1"


def test_build_touch_query_only_bumps_last_checked_at():
    sql, params = build_touch_query("hn", "49522897")

    assert "hn" not in sql
    assert "49522897" not in sql
    assert "last_checked_at" in sql
    assert "payload" not in sql
    assert "content_hash" not in sql
    assert params == ("hn", "49522897")
