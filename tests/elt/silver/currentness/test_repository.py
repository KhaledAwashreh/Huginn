from __future__ import annotations

import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier

import psycopg
import pytest

from huginn.elt.silver.context.models import SourceExtraction, SourceName
from huginn.elt.silver.currentness.models import (
    LifecycleFacts,
    LifecycleInput,
    ReconcileResult,
)
from huginn.elt.silver.currentness.repository import PostgresLifecycleRepository
from huginn.elt.silver.currentness.runner import run_reconcile
from tests.postgres_harness import provisioned_postgres


@pytest.fixture(scope="module")
def lifecycle_database_url() -> Iterator[str]:
    """Keep append-only lifecycle fixtures away from unrelated shared ELT tests."""
    with provisioned_postgres("huginn_lifecycle") as database_url:
        yield database_url


def _facts(
    stable_id: str,
    *,
    listing: str = "available",
    context: SourceExtraction | None = None,
) -> LifecycleFacts:
    return LifecycleFacts(
        listing_state=listing,  # type: ignore[arg-type]
        hiring_state="true",
        identity_state="consistent",
        reason="test observation",
        explicit_domain="example.test",
        occurred_at=None,
        context=context or _captured(stable_id),
    )


def _captured(stable_id: str, text: str = "Example listing") -> SourceExtraction:
    return SourceExtraction(
        source="hn",
        stable_id=stable_id,
        status="captured",
        source_url=f"https://news.ycombinator.com/item?id={stable_id}",
        normalized_text=text,
        source_fields={"title": text},
    )


def _bronze(
    connection: psycopg.Connection,
    stable_id: str,
    payload: object,
    *,
    source: str = "hn",
    fetched_at: datetime | None = None,
    last_checked_at: datetime | None = None,
) -> None:
    timestamp = datetime(2026, 1, 2, tzinfo=UTC)
    connection.execute(
        """INSERT INTO bronze.api_ingest
             (source, stable_id, payload, content_hash, run_id, fetched_at,
              last_checked_at)
           VALUES (%s, %s, %s, 'unchanged-hash', %s, %s, %s)""",
        (
            source,
            stable_id,
            psycopg.types.json.Jsonb(payload),
            uuid.uuid4(),
            fetched_at or timestamp,
            last_checked_at or timestamp,
        ),
    )


def _resolved(
    connection: psycopg.Connection,
    stable_id: str,
    *,
    key: str = "example.test",
    derivation: str = "domain_normalized",
) -> None:
    connection.execute(
        """INSERT INTO silver.resolved_signals
             (source, source_stable_id, resolved_company_key, company_name_raw,
              signal_type, key_derivation)
           VALUES ('hn', %s, %s, 'Example', 'hiring', %s)""",
        (stable_id, key, derivation),
    )


def _yc_resolved(connection: psycopg.Connection, stable_id: str, domain: str) -> None:
    connection.execute(
        """INSERT INTO silver.resolved_signals
             (source, source_stable_id, resolved_company_key, company_name_raw,
              signal_type, key_derivation)
           VALUES ('yc', %s, %s, 'Example YC Company', 'hiring',
                   'domain_normalized')""",
        (stable_id, domain),
    )


def _yc_payload(stable_id: str, website: str) -> dict[str, object]:
    return {
        "id": stable_id,
        "slug": f"company-{stable_id}",
        "name": "Example YC Company",
        "status": "Active",
        "website": website,
        "isHiring": True,
        "launched_at": 1_700_000_000,
        "one_liner": "A real source payload for lifecycle classification.",
    }


class _SelectedRepository:
    """Restrict a test run's actual PostgreSQL rows to explicit stable IDs."""

    def __init__(
        self,
        repository: PostgresLifecycleRepository,
        source: SourceName,
        stable_ids: set[str],
    ) -> None:
        self._repository = repository
        self._source = source
        self._stable_ids = stable_ids

    def read_inputs(
        self, source: SourceName, limit: int | None = None
    ) -> tuple[LifecycleInput, ...]:
        assert source == self._source
        return tuple(
            item
            for item in self._repository.read_inputs(source)
            if item.stable_id in self._stable_ids
        )

    def reconcile(self, item: LifecycleInput, facts: LifecycleFacts) -> ReconcileResult:
        return self._repository.reconcile(item, facts)


def _item(repository: PostgresLifecycleRepository, stable_id: str) -> LifecycleInput:
    return next(
        item for item in repository.read_inputs("hn") if item.stable_id == stable_id
    )


def _count(connection: psycopg.Connection, table: str, stable_id: str) -> int:
    return connection.execute(
        f"SELECT count(*) FROM silver.{table} WHERE source = 'hn' AND stable_id = %s",
        (stable_id,),
    ).fetchone()[0]


def test_read_inputs_returns_stable_id_order_and_full_raw_tokens(
    lifecycle_database_url: str,
) -> None:
    repository = PostgresLifecycleRepository(lifecycle_database_url)
    first_id, second_id = f"life-{uuid.uuid4().hex}-a", f"life-{uuid.uuid4().hex}-b"
    with psycopg.connect(lifecycle_database_url) as connection:
        _bronze(connection, second_id, {"body": "second"})
        _bronze(connection, first_id, {"body": "first"})

    items = tuple(
        item
        for item in repository.read_inputs("hn")
        if item.stable_id in {first_id, second_id}
    )
    assert [item.stable_id for item in items] == sorted((first_id, second_id))
    assert all(len(item.raw_token) == 32 for item in items)
    assert all(item.resolved_company_key is None for item in items)


def test_reconcile_is_idempotent_but_recreates_a_to_b_to_a(
    lifecycle_database_url: str,
) -> None:
    stable_id = f"life-{uuid.uuid4().hex}"
    repository = PostgresLifecycleRepository(lifecycle_database_url)
    with psycopg.connect(lifecycle_database_url) as connection:
        _bronze(connection, stable_id, {"body": "A"})
    original = _item(repository, stable_id)
    first = repository.reconcile(original, _facts(stable_id, listing="available"))
    repeated = repository.reconcile(original, _facts(stable_id, listing="withdrawn"))
    assert first.status == "created"
    assert repeated.status == "unchanged"
    assert repeated.observation_id == first.observation_id

    with psycopg.connect(lifecycle_database_url) as connection:
        connection.execute(
            "UPDATE bronze.api_ingest SET payload = %s "
            "WHERE source = 'hn' AND stable_id = %s",
            (psycopg.types.json.Jsonb({"body": "B"}), stable_id),
        )
    second_item = _item(repository, stable_id)
    second = repository.reconcile(second_item, _facts(stable_id))
    with psycopg.connect(lifecycle_database_url) as connection:
        connection.execute(
            "UPDATE bronze.api_ingest SET payload = %s "
            "WHERE source = 'hn' AND stable_id = %s",
            (psycopg.types.json.Jsonb({"body": "A"}), stable_id),
        )
    third = repository.reconcile(_item(repository, stable_id), _facts(stable_id))
    assert second.status == third.status == "created"
    assert len({first.observation_id, second.observation_id, third.observation_id}) == 3
    with psycopg.connect(lifecycle_database_url) as connection:
        assert _count(connection, "source_lifecycle_observation", stable_id) == 3


def test_concurrent_reconcile_creates_only_one_current_observation(
    lifecycle_database_url: str,
) -> None:
    stable_id = f"life-{uuid.uuid4().hex}"
    repository = PostgresLifecycleRepository(lifecycle_database_url)
    with psycopg.connect(lifecycle_database_url) as connection:
        _bronze(connection, stable_id, {"body": "same"})
    item = _item(repository, stable_id)
    barrier = Barrier(2)

    def reconcile_once():
        barrier.wait()
        return repository.reconcile(item, _facts(stable_id))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(lambda _index: reconcile_once(), range(2)))
    assert sorted(result.status for result in results) == ["created", "unchanged"]
    assert len({result.observation_id for result in results}) == 1
    with psycopg.connect(lifecycle_database_url) as connection:
        assert _count(connection, "source_lifecycle_observation", stable_id) == 1


def test_last_checked_only_change_does_not_create_history(
    lifecycle_database_url: str,
) -> None:
    stable_id = f"life-{uuid.uuid4().hex}"
    repository = PostgresLifecycleRepository(lifecycle_database_url)
    with psycopg.connect(lifecycle_database_url) as connection:
        _bronze(connection, stable_id, {"body": "steady"})
    item = _item(repository, stable_id)
    created = repository.reconcile(item, _facts(stable_id))
    with psycopg.connect(lifecycle_database_url) as connection:
        connection.execute(
            "UPDATE bronze.api_ingest SET last_checked_at = now() + interval '1 day' "
            "WHERE source = 'hn' AND stable_id = %s",
            (stable_id,),
        )
    unchanged = repository.reconcile(_item(repository, stable_id), _facts(stable_id))
    assert unchanged.status == "unchanged"
    assert unchanged.observation_id == created.observation_id
    with psycopg.connect(lifecycle_database_url) as connection:
        assert _count(connection, "source_lifecycle_observation", stable_id) == 1


def test_unchanged_reconcile_refreshes_pointer_metadata_only(
    lifecycle_database_url: str,
) -> None:
    stable_id = f"life-{uuid.uuid4().hex}"
    repository = PostgresLifecycleRepository(lifecycle_database_url)
    with psycopg.connect(lifecycle_database_url) as connection:
        _bronze(connection, stable_id, {"body": "steady"})
    item = _item(repository, stable_id)
    created = repository.reconcile(item, _facts(stable_id))
    old_reconciled_at = datetime(2000, 1, 1, tzinfo=UTC)
    with psycopg.connect(lifecycle_database_url) as connection:
        connection.execute(
            "UPDATE silver.source_currentness SET last_reconciled_at = %s "
            "WHERE source = 'hn' AND stable_id = %s",
            (old_reconciled_at, stable_id),
        )
        history_before = connection.execute(
            "SELECT * FROM silver.source_lifecycle_observation WHERE id = %s",
            (created.observation_id,),
        ).fetchone()

    unchanged = repository.reconcile(item, _facts(stable_id, listing="withdrawn"))

    with psycopg.connect(lifecycle_database_url) as connection:
        pointer_id, last_reconciled_at = connection.execute(
            "SELECT current_observation_id, last_reconciled_at "
            "FROM silver.source_currentness WHERE source = 'hn' AND stable_id = %s",
            (stable_id,),
        ).fetchone()
        history_after = connection.execute(
            "SELECT * FROM silver.source_lifecycle_observation WHERE id = %s",
            (created.observation_id,),
        ).fetchone()
        assert _count(connection, "source_lifecycle_observation", stable_id) == 1
        assert (
            connection.execute(
                "SELECT count(*) FROM silver.source_context_snapshot "
                "WHERE source = 'hn' AND stable_id = %s",
                (stable_id,),
            ).fetchone()[0]
            == 1
        )

    assert unchanged.status == "unchanged"
    assert unchanged.observation_id == pointer_id == created.observation_id
    assert last_reconciled_at > old_reconciled_at
    assert history_after == history_before


@pytest.mark.parametrize("change", ["payload", "resolution", "company"])
def test_stale_input_is_rejected_without_writes(
    lifecycle_database_url: str, change: str
) -> None:
    stable_id = f"life-{uuid.uuid4().hex}"
    domain = f"{uuid.uuid4().hex}.test"
    repository = PostgresLifecycleRepository(lifecycle_database_url)
    with psycopg.connect(lifecycle_database_url) as connection:
        _bronze(connection, stable_id, {"body": "before"})
        _resolved(connection, stable_id, key=domain)
    stale_input = _item(repository, stable_id)
    with psycopg.connect(lifecycle_database_url) as connection:
        if change == "payload":
            connection.execute(
                "UPDATE bronze.api_ingest SET payload = %s, content_hash = 'unchanged-hash' "
                "WHERE source = 'hn' AND stable_id = %s",
                (psycopg.types.json.Jsonb({"body": "after"}), stable_id),
            )
        elif change == "resolution":
            connection.execute(
                "UPDATE silver.resolved_signals SET resolved_company_key = %s "
                "WHERE source = 'hn' AND source_stable_id = %s",
                (f"changed-{domain}", stable_id),
            )
        else:
            connection.execute(
                "INSERT INTO gold.company (domain, name) VALUES (%s, 'Appeared')",
                (domain,),
            )
    result = repository.reconcile(stale_input, _facts(stable_id))
    assert result.status == "stale"
    assert result.observation_id is None
    with psycopg.connect(lifecycle_database_url) as connection:
        assert _count(connection, "source_lifecycle_observation", stable_id) == 0
        assert _count(connection, "source_currentness", stable_id) == 0


def test_failed_context_is_recorded_without_snapshot(
    lifecycle_database_url: str,
) -> None:
    stable_id = f"life-{uuid.uuid4().hex}"
    repository = PostgresLifecycleRepository(lifecycle_database_url)
    with psycopg.connect(lifecycle_database_url) as connection:
        _bronze(connection, stable_id, {"body": "raw"})
    failed = SourceExtraction(
        source="hn",
        stable_id=stable_id,
        status="failed",
        reason="source page unavailable",
    )
    result = repository.reconcile(
        _item(repository, stable_id), _facts(stable_id, context=failed)
    )
    assert result.status == "created"
    with psycopg.connect(lifecycle_database_url) as connection:
        row = connection.execute(
            "SELECT snapshot_id FROM silver.source_lifecycle_observation WHERE id = %s",
            (result.observation_id,),
        ).fetchone()
        assert row == (None,)


def test_jsonb_malformed_rows_are_partial_while_valid_row_is_reconciled(
    lifecycle_database_url: str,
) -> None:
    malformed_null_id = f"life-yc-{uuid.uuid4().hex}-null"
    malformed_list_id = f"life-yc-{uuid.uuid4().hex}-list"
    valid_id = f"life-yc-{uuid.uuid4().hex}-valid"
    selected_ids = {malformed_null_id, malformed_list_id, valid_id}
    repository = PostgresLifecycleRepository(lifecycle_database_url)
    with psycopg.connect(lifecycle_database_url) as connection:
        _bronze(connection, malformed_null_id, None, source="yc")
        _bronze(connection, malformed_list_id, ["unexpected", "array"], source="yc")
        _bronze(
            connection,
            valid_id,
            _yc_payload(valid_id, "https://normal-company.example"),
            source="yc",
        )
        connection.execute(
            "INSERT INTO gold.company (domain, name) "
            "VALUES ('normal-company.example', 'Normal Company')"
        )
        _yc_resolved(connection, valid_id, "normal-company.example")

    report = run_reconcile(
        "yc",
        _SelectedRepository(repository, "yc", selected_ids),
    )

    assert report["status"] == "partial"
    assert report["selected_count"] == 3
    assert report["classified_count"] == report["completed_count"] == 3
    assert report["invalid_listing_count"] == 2
    assert report["reconcile_counts"] == {
        "created": 3,
        "unchanged": 0,
        "stale": 0,
    }
    with psycopg.connect(lifecycle_database_url) as connection:
        rows = connection.execute(
            """SELECT stable_id, listing_state, reason, snapshot_id
               FROM silver.source_lifecycle_observation
               WHERE source = 'yc' AND stable_id = ANY(%s)""",
            (list(selected_ids),),
        ).fetchall()
    observations = {row[0]: row[1:] for row in rows}
    assert observations[malformed_null_id][:2] == ("invalid", "malformed_payload")
    assert observations[malformed_list_id][:2] == ("invalid", "malformed_payload")
    assert observations[malformed_null_id][2] is None
    assert observations[malformed_list_id][2] is None
    assert observations[valid_id][0] == "available"
    assert observations[valid_id][2] is not None


def test_yc_domain_association_history_tracks_a_to_b_to_a(
    lifecycle_database_url: str,
) -> None:
    stable_id = f"life-yc-{uuid.uuid4().hex}"
    domain_a = f"a-{uuid.uuid4().hex}.example"
    domain_b = f"b-{uuid.uuid4().hex}.example"
    website_a = f"https://{domain_a}"
    website_b = f"https://{domain_b}"
    repository = PostgresLifecycleRepository(lifecycle_database_url)
    with psycopg.connect(lifecycle_database_url) as connection:
        _bronze(connection, stable_id, _yc_payload(stable_id, website_a), source="yc")
        connection.execute(
            "INSERT INTO gold.company (domain, name) VALUES (%s, 'Company A'), "
            "(%s, 'Company B')",
            (domain_a, domain_b),
        )
        _yc_resolved(connection, stable_id, domain_a)

    selected = _SelectedRepository(repository, "yc", {stable_id})
    first_report = run_reconcile("yc", selected)
    with psycopg.connect(lifecycle_database_url) as connection:
        company_a_id = connection.execute(
            "SELECT id FROM gold.company WHERE domain = %s", (domain_a,)
        ).fetchone()[0]
        company_b_id = connection.execute(
            "SELECT id FROM gold.company WHERE domain = %s", (domain_b,)
        ).fetchone()[0]
        # Keep a complete copy of A's first lifecycle fact row for the final check.
        original_a = connection.execute(
            """SELECT id, raw_token, resolution_token, company_id, snapshot_id,
                      listing_state, hiring_state, identity_state, reason, observed_at
               FROM silver.source_lifecycle_observation
               WHERE source = 'yc' AND stable_id = %s""",
            (stable_id,),
        ).fetchone()
        company_a_id = connection.execute(
            "SELECT id FROM gold.company WHERE domain = %s", (domain_a,)
        ).fetchone()[0]

    with psycopg.connect(lifecycle_database_url) as connection:
        connection.execute(
            "UPDATE bronze.api_ingest SET payload = %s "
            "WHERE source = 'yc' AND stable_id = %s",
            (psycopg.types.json.Jsonb(_yc_payload(stable_id, website_b)), stable_id),
        )
        connection.execute(
            "UPDATE silver.resolved_signals SET resolved_company_key = %s "
            "WHERE source = 'yc' AND source_stable_id = %s",
            (domain_b, stable_id),
        )
    second_report = run_reconcile("yc", selected)

    with psycopg.connect(lifecycle_database_url) as connection:
        connection.execute(
            "UPDATE bronze.api_ingest SET payload = %s "
            "WHERE source = 'yc' AND stable_id = %s",
            (psycopg.types.json.Jsonb(_yc_payload(stable_id, website_a)), stable_id),
        )
        connection.execute(
            "UPDATE silver.resolved_signals SET resolved_company_key = %s "
            "WHERE source = 'yc' AND source_stable_id = %s",
            (domain_a, stable_id),
        )
    third_report = run_reconcile("yc", selected)

    assert all(
        report["status"] == "complete"
        and report["reconcile_counts"] == {"created": 1, "unchanged": 0, "stale": 0}
        for report in (first_report, second_report, third_report)
    )
    with psycopg.connect(lifecycle_database_url) as connection:
        observations = connection.execute(
            """SELECT id, raw_token, resolution_token, company_id, snapshot_id,
                      listing_state, hiring_state, identity_state, reason, observed_at
               FROM silver.source_lifecycle_observation
               WHERE source = 'yc' AND stable_id = %s ORDER BY observed_at, id""",
            (stable_id,),
        ).fetchall()
    assert len(observations) == 3
    assert len({row[0] for row in observations}) == 3
    assert [row[3] for row in observations] == [
        company_a_id,
        company_b_id,
        company_a_id,
    ]
    assert observations[0][1] != observations[1][1]
    assert observations[0][2] != observations[1][2]
    assert observations[0][4] == observations[2][4]
    assert observations[0][5:9] == (
        "available",
        "true",
        "consistent",
        "yc_status_available",
    )
    assert observations[0] == original_a


def test_snapshot_and_observation_roll_back_together(
    lifecycle_database_url: str,
) -> None:
    stable_id = f"life-{uuid.uuid4().hex}"
    repository = PostgresLifecycleRepository(lifecycle_database_url)
    with psycopg.connect(lifecycle_database_url) as connection:
        _bronze(connection, stable_id, {"body": "raw"})
    bad_facts = LifecycleFacts(
        listing_state="not-a-state",  # type: ignore[arg-type]
        hiring_state="true",
        identity_state="consistent",
        reason="trigger a database constraint",
        explicit_domain=None,
        occurred_at=None,
        context=_captured(stable_id),
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        repository.reconcile(_item(repository, stable_id), bad_facts)
    with psycopg.connect(lifecycle_database_url) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM silver.source_context_snapshot "
                "WHERE source = 'hn' AND stable_id = %s",
                (stable_id,),
            ).fetchone()[0]
            == 0
        )
        assert _count(connection, "source_lifecycle_observation", stable_id) == 0
        assert _count(connection, "source_currentness", stable_id) == 0


def test_observation_history_rejects_update_and_delete(
    lifecycle_database_url: str,
) -> None:
    stable_id = f"life-{uuid.uuid4().hex}"
    repository = PostgresLifecycleRepository(lifecycle_database_url)
    with psycopg.connect(lifecycle_database_url) as connection:
        _bronze(connection, stable_id, {"body": "raw"})
    result = repository.reconcile(_item(repository, stable_id), _facts(stable_id))
    with (
        psycopg.connect(lifecycle_database_url) as connection,
        pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
    ):
        connection.execute(
            "UPDATE silver.source_lifecycle_observation SET reason = 'edited' "
            "WHERE id = %s",
            (result.observation_id,),
        )
    with (
        psycopg.connect(lifecycle_database_url) as connection,
        pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
    ):
        connection.execute(
            "DELETE FROM silver.source_lifecycle_observation WHERE id = %s",
            (result.observation_id,),
        )
