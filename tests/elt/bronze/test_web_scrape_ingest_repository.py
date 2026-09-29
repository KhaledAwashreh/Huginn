from psycopg.types.json import Jsonb

from huginn.elt.bronze.repositories.web_scrape_ingest_repository import (
    build_lookup_query,
    build_touch_query,
    build_write_query,
)


def test_build_lookup_query_targets_web_scrape_table_with_bound_parameters():
    sql, params = build_lookup_query("eu_startups", "brightroom")

    assert "eu_startups" not in sql
    assert "brightroom" not in sql
    assert "bronze.web_scrape_ingest" in sql
    assert "content_hash" in sql
    assert params == ("eu_startups", "brightroom")


def test_build_write_query_parameterizes_jsonb_and_uuid_run_id():
    payload = {"html": "<main>Brightroom</main>"}
    sql, params = build_write_query(
        "eu_startups", "brightroom", payload, "hash123", "run-uuid-1"
    )

    assert "brightroom" not in sql
    assert "hash123" not in sql
    assert "run-uuid-1" not in sql
    assert "bronze.web_scrape_ingest" in sql
    assert "ON CONFLICT" in sql
    assert "EXCLUDED.source <> 'eu_startups'" in sql
    assert "payload ->> 'lastmod' IS NULL" in sql
    assert "%s::uuid" in sql
    assert params[:2] == ("eu_startups", "brightroom")
    assert isinstance(params[2], Jsonb)
    assert params[2].obj == payload
    assert params[3:] == ("hash123", "run-uuid-1")


def test_build_touch_query_only_updates_last_checked_at():
    sql, params = build_touch_query("eu_startups", "brightroom")

    assert "bronze.web_scrape_ingest" in sql
    assert "last_checked_at" in sql
    assert "payload" not in sql
    assert "content_hash" not in sql
    assert params == ("eu_startups", "brightroom")
