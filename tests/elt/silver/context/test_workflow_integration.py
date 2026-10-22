from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg import sql

from huginn.elt.silver.context.__main__ import main
from huginn.elt.silver.context.repository import SourceContextRepository


def _payload_hash(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _checksums(database_url: str) -> dict[str, str]:
    with psycopg.connect(database_url) as connection:
        tables = connection.execute(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_type = 'BASE TABLE' AND table_schema = ANY(%s) "
            "AND table_name NOT IN ('source_context_snapshot', 'source_context_run', 'source_context_outcome') "
            "ORDER BY table_schema, table_name",
            (["bronze", "silver", "gold", "operational"],),
        ).fetchall()
        result = {}
        for schema, table in tables:
            rows = connection.execute(
                sql.SQL("SELECT * FROM {}.{}").format(
                    sql.Identifier(schema), sql.Identifier(table)
                )
            ).fetchall()
            canonical_rows = sorted(
                json.dumps(row, sort_keys=True, default=str, separators=(",", ":"))
                for row in rows
            )
            result[f"{schema}.{table}"] = hashlib.sha256(
                json.dumps(canonical_rows, separators=(",", ":")).encode()
            ).hexdigest()
        return result


def _sidecar_counts(database_url: str) -> tuple[int, int, int]:
    with psycopg.connect(database_url) as connection:
        snapshots = connection.execute(
            "SELECT count(*) FROM silver.source_context_snapshot"
        ).fetchone()[0]
        runs = connection.execute(
            "SELECT count(*) FROM silver.source_context_run"
        ).fetchone()[0]
        outcomes = connection.execute(
            "SELECT count(*) FROM silver.source_context_outcome"
        ).fetchone()[0]
    return snapshots, runs, outcomes


def test_cli_audit_capture_twice_preserves_legacy_layers_and_accounts_for_inputs(
    integration_database_url: str, tmp_path
) -> None:
    suffix = uuid.uuid4().hex
    ids = {
        "hn": [f"hn-{suffix}"],
        "yc": [f"yc-active-{suffix}", f"yc-inactive-{suffix}"],
        "eu_startups": [f"eu-{suffix}"],
    }
    username = f"context-{suffix}"
    company_domain = f"context-{suffix}.example.test"
    company_id = None
    run_ids: list[uuid.UUID] = []
    hn_payload = {
        "id": ids["hn"][0],
        "type": "comment",
        "text": "Remote | Full-time role<p>Build useful tools.",
        "time": 1_700_000_000,
    }
    yc_payloads = [
        {
            "id": ids["yc"][0],
            "slug": f"active-{suffix}",
            "name": "Sanitized Active",
            "one_liner": "Short",
            "long_description": "Long source description",
            "tags": ["B2B"],
            "regions": ["Remote"],
            "industries": ["Software"],
            "batch": "Winter 2024",
            "status": "Active",
            "team_size": 0,
            "isHiring": False,
            "launched_at": 1_700_000_000,
        },
        {
            "id": ids["yc"][1],
            "slug": f"inactive-{suffix}",
            "name": "Sanitized Acquired",
            "one_liner": "Short acquired",
            "status": "Acquired",
            "team_size": 1,
        },
    ]
    eu_payload = {
        "url": f"https://www.eu-startups.com/directory/{ids['eu_startups'][0]}/",
        "html": '<div class="wpbdp-listing-single"><h2 class="listing-title">Sanitized EU</h2><div class="wpbdp-field-business_description"><div class="value">Short description</div></div><div class="wpbdp-field-long_business_description"><div class="value">Long description</div></div><div class="wpbdp-field-category"><div class="value">Software</div></div></div>',
        "lastmod": "2025-01-01T00:00:00+00:00",
    }
    run_uuid = uuid.uuid4()
    gold_sources = [
        ("hn", ids["hn"][0]),
        ("yc", ids["yc"][0]),
        ("eu_startups", ids["eu_startups"][0]),
    ]

    try:
        with psycopg.connect(integration_database_url) as connection:
            for source, stable_id, payload, table in (
                ("hn", ids["hn"][0], hn_payload, "bronze.api_ingest"),
                ("yc", ids["yc"][0], yc_payloads[0], "bronze.api_ingest"),
                ("yc", ids["yc"][1], yc_payloads[1], "bronze.api_ingest"),
                (
                    "eu_startups",
                    ids["eu_startups"][0],
                    eu_payload,
                    "bronze.web_scrape_ingest",
                ),
            ):
                connection.execute(
                    f"INSERT INTO {table} (source, stable_id, payload, content_hash, run_id) VALUES (%s, %s, %s, %s, %s)",
                    (
                        source,
                        stable_id,
                        json.dumps(payload),
                        _payload_hash(payload),
                        run_uuid,
                    ),
                )
            connection.execute(
                "INSERT INTO silver.hn_postings (stable_id, company_name_raw, signal_type, description) VALUES (%s, 'Sanitized HN', 'hiring', 'Legacy HN')",
                (ids["hn"][0],),
            )
            connection.execute(
                "INSERT INTO silver.yc_listings (stable_id, company_name_raw, signal_type, description, company_status, team_size) VALUES (%s, 'Sanitized YC', 'other', 'Legacy YC', 'Active', 0)",
                (ids["yc"][0],),
            )
            connection.execute(
                "INSERT INTO silver.eu_startups_listings (stable_id, company_name_raw, signal_type, description) VALUES (%s, 'Sanitized EU', 'other', 'Legacy EU')",
                (ids["eu_startups"][0],),
            )
            for source, stable_id in gold_sources:
                connection.execute(
                    "INSERT INTO silver.resolved_signals (source, source_stable_id, resolved_company_key, company_name_raw, signal_type, key_derivation) VALUES (%s, %s, %s, 'Sanitized company', 'other', 'unresolved')",
                    (source, stable_id, f"unresolved:{stable_id}"),
                )
            company_id = connection.execute(
                "INSERT INTO gold.company (domain, name) VALUES (%s, 'Sanitized company') RETURNING id",
                (company_domain,),
            ).fetchone()[0]
            for source, stable_id in gold_sources:
                connection.execute(
                    "INSERT INTO gold.company_signal (company_id, source, source_stable_id, signal_type, occurred_at, description) VALUES (%s, %s, %s, 'other', %s, 'Legacy gold')",
                    (company_id, source, stable_id, datetime(2025, 1, 1, tzinfo=UTC)),
                )
            connection.execute(
                "INSERT INTO operational.accounts (username, password_hash) VALUES (%s, 'sanitized-test-hash')",
                (username,),
            )

        repository = SourceContextRepository(integration_database_url)
        baseline = _checksums(integration_database_url)
        sidecar_baseline = _sidecar_counts(integration_database_url)
        for source in ("hn", "yc", "eu_startups"):
            assert (
                main(
                    ["audit", "--source", source], repository_factory=lambda: repository
                )
                == 0
            )
        assert _checksums(integration_database_url) == baseline
        assert _sidecar_counts(integration_database_url) == sidecar_baseline

        for _ in range(2):
            for source, source_ids in ids.items():
                output = tmp_path / f"{source}-{_}.json"
                assert (
                    main(
                        ["capture", "--source", source, "--summary", str(output)],
                        repository_factory=lambda: repository,
                    )
                    == 0
                )
                report = json.loads(output.read_text())
                assert report["input_count"] == len(source_ids)
                assert sum(report["outcomes"].values()) == len(source_ids)
                assert report["persistence"]["input_count"] == len(source_ids)
                assert report["persistence"]["status"] == "complete"
                run_ids.append(uuid.UUID(report["persistence"]["run_id"]))
        after = _checksums(integration_database_url)
        assert after == baseline
        with psycopg.connect(integration_database_url) as connection:
            snapshots = connection.execute(
                "SELECT source, stable_id, count(*) FROM silver.source_context_snapshot WHERE stable_id = ANY(%s) GROUP BY source, stable_id",
                ([value for values in ids.values() for value in values],),
            ).fetchall()
            assert len(snapshots) == 4
            assert all(count == 1 for _, _, count in snapshots)
            inactive = connection.execute(
                "SELECT count(*) FROM silver.yc_listings WHERE stable_id = %s",
                (ids["yc"][1],),
            ).fetchone()[0]
            assert inactive == 0

        details_path = tmp_path / "yc-details.json"
        assert (
            main(
                [
                    "audit",
                    "--source",
                    "yc",
                    "--limit",
                    "1",
                    "--details",
                    str(details_path),
                ],
                repository_factory=lambda: repository,
            )
            == 0
        )
        details = json.loads(details_path.read_text())
        expected_first = min(
            ids["yc"], key=lambda item: (hashlib.md5(item.encode()).hexdigest(), item)
        )
        assert [row["stable_id"] for row in details["records"]] == [expected_first]
    finally:
        with psycopg.connect(integration_database_url) as connection:
            if run_ids:
                connection.execute(
                    "DELETE FROM silver.source_context_run WHERE id = ANY(%s)",
                    (run_ids,),
                )
            all_ids = [value for values in ids.values() for value in values]
            connection.execute(
                "DELETE FROM silver.source_context_snapshot WHERE stable_id = ANY(%s)",
                (all_ids,),
            )
            connection.execute(
                "DELETE FROM gold.company_signal WHERE source_stable_id = ANY(%s)",
                (all_ids,),
            )
            connection.execute(
                "DELETE FROM silver.resolved_signals WHERE source_stable_id = ANY(%s)",
                (all_ids,),
            )
            connection.execute(
                "DELETE FROM silver.hn_postings WHERE stable_id = ANY(%s)", (ids["hn"],)
            )
            connection.execute(
                "DELETE FROM silver.yc_listings WHERE stable_id = ANY(%s)", (ids["yc"],)
            )
            connection.execute(
                "DELETE FROM silver.eu_startups_listings WHERE stable_id = ANY(%s)",
                (ids["eu_startups"],),
            )
            connection.execute(
                "DELETE FROM gold.company WHERE domain = %s", (company_domain,)
            )
            connection.execute(
                "DELETE FROM operational.accounts WHERE username = %s", (username,)
            )
            connection.execute(
                "DELETE FROM bronze.api_ingest WHERE source IN ('hn', 'yc') AND stable_id = ANY(%s)",
                (ids["hn"] + ids["yc"],),
            )
            connection.execute(
                "DELETE FROM bronze.web_scrape_ingest WHERE source = 'eu_startups' AND stable_id = ANY(%s)",
                (ids["eu_startups"],),
            )


def test_capture_cli_reports_failed_record_status(
    integration_database_url: str, tmp_path: Path
) -> None:
    stable_id = f"yc-malformed-{uuid.uuid4().hex}"
    run_uuid = uuid.uuid4()
    payload = {"id": stable_id, "slug": "malformed", "isHiring": "false"}
    with psycopg.connect(integration_database_url) as connection:
        connection.execute(
            "INSERT INTO bronze.api_ingest (source, stable_id, payload, content_hash, run_id) VALUES ('yc', %s, %s, %s, %s)",
            (stable_id, json.dumps(payload), _payload_hash(payload), run_uuid),
        )
    run_ids: list[uuid.UUID] = []
    try:
        output_path = tmp_path / "failure.json"
        result = main(
            ["capture", "--source", "yc", "--summary", str(output_path)],
            repository_factory=lambda: SourceContextRepository(
                integration_database_url
            ),
        )
        report = json.loads(output_path.read_text())
        assert result == 1
        assert report["outcomes"]["failed"] == 1
        assert report["persistence"]["failed_count"] == 1
        assert report["persistence"]["status"] == "failed"
        run_ids.append(uuid.UUID(report["persistence"]["run_id"]))
    finally:
        with psycopg.connect(integration_database_url) as connection:
            if run_ids:
                connection.execute(
                    "DELETE FROM silver.source_context_run WHERE id = ANY(%s)",
                    (run_ids,),
                )
            connection.execute(
                "DELETE FROM bronze.api_ingest WHERE source = 'yc' AND stable_id = %s",
                (stable_id,),
            )
