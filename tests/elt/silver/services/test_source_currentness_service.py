from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from huginn.elt.silver.infrastructure.json_report_writer import (
    FilesystemJsonReportWriter,
)
from huginn.elt.silver.models.lifecycle_facts import LifecycleFacts
from huginn.elt.silver.models.lifecycle_input import LifecycleInput
from huginn.elt.silver.models.reconcile_result import ReconcileResult
from huginn.elt.silver.models.source_extraction import SourceExtraction
from huginn.elt.silver.services.source_currentness import run_audit, run_reconcile

_NOW = datetime(2026, 10, 22, tzinfo=UTC)
_DEFAULT_COMPANY_ID = UUID(int=1)


def _item(
    stable_id: str,
    *,
    source: str = "yc",
    raw_token: str | None = None,
    resolution_token: str | None = None,
    company_id: UUID | None = _DEFAULT_COMPANY_ID,
) -> LifecycleInput:
    return LifecycleInput(
        source=source,  # type: ignore[arg-type]
        stable_id=stable_id,
        payload={"id": stable_id, "name": "Do not report this value"},
        raw_token=raw_token or f"raw-{stable_id}",
        resolution_token=resolution_token or f"resolution-{stable_id}",
        resolved_company_key="example.test",
        key_derivation="domain_normalized",
        company_id=company_id,
        fetched_at=_NOW,
        last_checked_at=_NOW,
    )


def _facts(
    item: LifecycleInput,
    *,
    listing: str = "available",
    hiring: str = "unknown",
    identity: str = "consistent",
    reason: str = "source_status_active",
) -> LifecycleFacts:
    return LifecycleFacts(
        listing_state=listing,  # type: ignore[arg-type]
        hiring_state=hiring,  # type: ignore[arg-type]
        identity_state=identity,  # type: ignore[arg-type]
        reason=reason,
        explicit_domain="example.test",
        occurred_at=None,
        context=SourceExtraction(
            source=item.source,
            stable_id=item.stable_id,
            status="captured",
        ),
    )


class FakeRepository:
    def __init__(self, items: tuple[LifecycleInput, ...]) -> None:
        self.items = items
        self.reconciled: list[str] = []
        self.fail_on: str | None = None

    def read_inputs(self, source: str, limit: int | None = None):
        selected = tuple(item for item in self.items if item.source == source)
        return selected if limit is None else selected[:limit]

    def reconcile(self, item: LifecycleInput, facts: LifecycleFacts):
        self.reconciled.append(item.stable_id)
        if self.fail_on == item.stable_id:
            raise RuntimeError("sensitive database detail")
        return ReconcileResult("created", uuid4())


def test_audit_is_aggregate_only_and_fingerprints_expected_raw_and_resolution_tokens(
    tmp_path,
):
    items = (_item("yc-1"), _item("yc-2", raw_token="raw-other"))
    repo = FakeRepository(items)
    report_path = tmp_path / "audit.json"

    report = run_audit(
        "yc",
        repo,
        classifier=_facts,
        summary_path=report_path,
        report_writer=FilesystemJsonReportWriter(),
    )

    encoded = report_path.read_text()
    assert json.loads(encoded) == report
    assert report["mode"] == "audit"
    assert report["source"] == "yc"
    assert report["policy_version"] == "source-lifecycle-v1"
    assert report["context_version"] == "yc-context-v1"
    assert report["selected_count"] == 2
    assert report["selection"] == {"limit": None, "scope": "all_stored_inputs"}
    assert report["states"] == {
        "listing": {"available": 2},
        "hiring": {"unknown": 2},
        "identity": {"consistent": 2},
    }
    assert report["reasons"] == {"source_status_active": 2}
    assert len(report["input_fingerprint"]) == 64
    assert "Do not report this value" not in encoded
    assert "example.test" not in encoded
    assert "stable_id" not in encoded
    assert repo.reconciled == []


def test_limited_audit_identifies_sample_scope_without_claiming_full_coverage():
    repo = FakeRepository((_item("yc-1"), _item("yc-2"), _item("yc-3")))

    report = run_audit("yc", repo, limit=1, classifier=_facts)

    assert report["selected_count"] == 1
    assert report["selection"] == {"limit": 1, "scope": "limited_sample"}
    assert "available_input_count" not in report
    assert "coverage" not in report


def test_unknown_listing_is_reported_as_a_state_without_becoming_an_error():
    repo = FakeRepository((_item("yc-unknown"),))

    report = run_audit(
        "yc",
        repo,
        classifier=lambda item: _facts(
            item, listing="unknown", reason="status_missing"
        ),
    )

    assert report["status"] == "complete"
    assert report["states"]["listing"] == {"unknown": 1}
    assert report["invalid_or_unknown_count"] == 1
    assert report["invalid_listing_count"] == 0


def test_fingerprint_changes_when_either_input_signature_changes():
    raw_changed = FakeRepository((_item("yc-1", raw_token="new-raw"),))
    resolution_changed = FakeRepository(
        (_item("yc-1", resolution_token="new-resolution"),)
    )
    baseline = run_audit("yc", FakeRepository((_item("yc-1"),)), classifier=_facts)

    assert (
        run_audit("yc", raw_changed, classifier=_facts)["input_fingerprint"]
        != baseline["input_fingerprint"]
    )
    assert (
        run_audit("yc", resolution_changed, classifier=_facts)["input_fingerprint"]
        != baseline["input_fingerprint"]
    )


def test_company_appearance_changes_fingerprint_only():
    missing_company = FakeRepository((_item("yc-1", company_id=None),))
    appeared_company = FakeRepository((_item("yc-1", company_id=_DEFAULT_COMPANY_ID),))

    missing_report = run_audit("yc", missing_company, classifier=_facts)
    appeared_report = run_audit("yc", appeared_company, classifier=_facts)

    assert missing_report["input_fingerprint"] != appeared_report["input_fingerprint"]
    assert missing_report["states"] == appeared_report["states"]
    assert missing_report["reasons"] == appeared_report["reasons"]


def test_audit_keyboard_interrupt_persists_partial_aggregate(tmp_path):
    repo = FakeRepository((_item("yc-1"), _item("yc-2")))
    report_path = tmp_path / "audit-interrupted.json"

    def interrupt_on_second(item):
        if item.stable_id == "yc-2":
            raise KeyboardInterrupt
        return _facts(item)

    report = run_audit(
        "yc",
        repo,
        classifier=interrupt_on_second,
        summary_path=report_path,
        report_writer=FilesystemJsonReportWriter(),
    )

    assert report["status"] == "partial"
    assert report["error_type"] == "KeyboardInterrupt"
    assert report["completed_count"] == 1
    assert json.loads(report_path.read_text()) == report


def test_reconcile_counts_statuses_and_returns_non_complete_for_stale_or_unknown():
    items = (_item("yc-1"), _item("yc-2"), _item("yc-3"))
    repo = FakeRepository(items)

    def classify(item):
        if item.stable_id == "yc-3":
            return _facts(item, listing="unknown", reason="status_missing")
        return _facts(item)

    def reconcile(item, facts):
        return ReconcileResult(
            "stale" if item.stable_id == "yc-2" else "created", uuid4()
        )

    report = run_reconcile("yc", repo, classifier=classify, reconcile=reconcile)

    assert report["mode"] == "reconcile"
    assert report["status"] == "partial"
    assert report["reconcile_counts"] == {"created": 2, "unchanged": 0, "stale": 1}
    assert report["states"]["listing"] == {"available": 2, "unknown": 1}
    assert report["invalid_or_unknown_count"] == 1


def test_reconcile_preflights_summary_path_before_repository_writes(tmp_path):
    target = tmp_path / "report.json"
    target.mkdir()
    repo = FakeRepository((_item("yc-1"),))
    try:
        run_reconcile(
            "yc",
            repo,
            classifier=_facts,
            summary_path=target,
            report_writer=FilesystemJsonReportWriter(),
        )
    except OSError:
        pass
    else:
        raise AssertionError("invalid summary path should fail")
    assert repo.reconciled == []


def test_reconcile_partial_error_persists_sanitized_progress_report(tmp_path):
    repo = FakeRepository((_item("yc-1"), _item("yc-2")))
    repo.fail_on = "yc-2"
    report_path = tmp_path / "partial.json"

    report = run_reconcile(
        "yc",
        repo,
        classifier=_facts,
        summary_path=report_path,
        report_writer=FilesystemJsonReportWriter(),
    )

    assert report["status"] == "partial"
    assert report["completed_count"] == 1
    assert report["classified_count"] == 2
    assert report["error_type"] == "RuntimeError"
    assert "sensitive database detail" not in report_path.read_text()
    assert json.loads(report_path.read_text()) == report


def test_reconcile_keyboard_interrupt_persists_progress_and_created_count(tmp_path):
    items = (_item("yc-1"), _item("yc-2"))
    repo = FakeRepository(items)
    report_path = tmp_path / "interrupted.json"

    def interrupt_on_second_write(item, facts):
        if item.stable_id == "yc-2":
            raise KeyboardInterrupt
        return ReconcileResult("created", uuid4())

    report = run_reconcile(
        "yc",
        repo,
        classifier=_facts,
        reconcile=interrupt_on_second_write,
        summary_path=report_path,
        report_writer=FilesystemJsonReportWriter(),
    )

    assert report["status"] == "partial"
    assert report["error_type"] == "KeyboardInterrupt"
    assert report["completed_count"] == 1
    assert report["reconcile_counts"] == {"created": 1, "unchanged": 0, "stale": 0}
    assert json.loads(report_path.read_text()) == report
