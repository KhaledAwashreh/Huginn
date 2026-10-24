from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from huginn.elt.silver.infrastructure.json_report_writer import (
    FilesystemJsonReportWriter,
)
from huginn.elt.silver.models.source_extraction import SourceExtraction
from huginn.elt.silver.services.source_context import run_audit, run_capture


@dataclass(frozen=True)
class Input:
    source: str
    stable_id: str
    payload: dict[str, object]
    fetched_at: datetime = datetime(2024, 1, 1, tzinfo=UTC)
    last_checked_at: datetime = datetime(2025, 1, 1, tzinfo=UTC)


class FakeRepository:
    def __init__(self, inputs: list[Input]) -> None:
        self.inputs = inputs
        self.read_calls: list[tuple[str, int | None, bool]] = []
        self.persisted = None
        self.snapshot_calls: list[tuple[str, int | None]] = []

    def read_inputs(
        self, source: str, limit: int | None = None, *, read_only: bool = True
    ):
        self.read_calls.append((source, limit, read_only))
        return self.inputs

    def count_inputs(self, source: str) -> int:
        return len(self.inputs)

    def coverage_counts(self, source: str) -> dict[str, int]:
        return {"bronze": len(self.inputs), "source_staging": 2, "resolved_signals": 1}

    def read_audit_snapshot(self, source: str, limit: int | None = None):
        self.snapshot_calls.append((source, limit))
        return type(
            "Snapshot",
            (),
            {
                "inputs": tuple(self.inputs),
                "available_count": len(self.inputs),
                "coverage_counts": {
                    "bronze": len(self.inputs),
                    "silver_staging": 2,
                    "silver_resolved": 1,
                    "silver_unresolved": 2,
                    "gold_signals": 1,
                },
                "downstream_by_stable_id": {
                    "2": {
                        "silver_staging_description": "old staging",
                        "silver_resolved_description": "old resolved",
                        "silver_key_derivation": "domain_normalized",
                        "gold_description": "old gold",
                    }
                },
            },
        )()

    def persist_run(self, run):
        self.persisted = run
        return {"run_id": "test-run", "status": "succeeded"}


def _normalize(payload: dict[str, object]) -> SourceExtraction:
    status = payload.get("outcome", "captured")
    return SourceExtraction(
        source="yc",
        stable_id=str(payload.get("id")) if payload.get("id") is not None else None,
        status=status,  # type: ignore[arg-type]
        reason="test exclusion" if status == "excluded" else None,
        normalized_text=payload.get("text")
        if isinstance(payload.get("text"), str)
        else None,
        source_fields={
            key: payload[key]
            for key in ("one_liner", "long_description", "isHiring", "team_size")
            if key in payload
        },
    )


def test_run_audit_reads_read_only_and_accounts_for_all_outcomes():
    repo = FakeRepository(
        [
            Input(
                "yc",
                "2",
                {
                    "id": 2,
                    "slug": "sample-co",
                    "text": "two",
                    "one_liner": "short",
                    "long_description": "long",
                    "isHiring": False,
                    "team_size": 0,
                },
            ),
            Input("yc", "1", {"id": 1, "outcome": "excluded"}),
            Input("yc", "3", {"id": 3, "outcome": "failed"}),
        ]
    )

    report = run_audit("yc", repo, normalizer=_normalize)

    assert repo.snapshot_calls == [("yc", None)]
    assert repo.read_calls == []
    assert report["outcomes"] == {"captured": 1, "excluded": 1, "failed": 1}
    assert report["input_count"] == 3
    assert report["field_coverage"]["one_liner"] == {"present": 1, "known": 1}
    assert report["source_metrics"] == {
        "normalized_text_records": 1,
        "header_span_records": 0,
        "body_span_records": 0,
        "header_characters": 0,
        "body_characters": 0,
        "source_time_fields": {},
        "one_liner": 1,
        "long_description": 1,
        "both_descriptions": 1,
        "one_liner_only": 0,
        "long_description_only": 0,
        "hiring_true": 0,
        "hiring_false": 1,
        "hiring_unknown": 0,
        "team_size_zero": 1,
        "status_known": 0,
        "status_unknown": 1,
        "inactive_or_acquired_status": 0,
        "unprojected_source_fields": {
            "one_liner": 1,
            "tags": 0,
            "tags_highlighted": 0,
            "regions": 0,
            "industry": 0,
            "subindustry": 0,
            "isHiring": 1,
        },
    }
    assert report["coverage"] == {
        "bronze": 3,
        "source_staging": 2,
        "resolved_signals": 3,
        "resolved_linked_signals": 1,
        "unresolved_signals": 2,
        "gold": 1,
    }
    assert report["comparisons"]["silver_staging"]["different"] == 1
    assert report["comparisons"]["silver_resolved"]["different"] == 1
    assert report["comparisons"]["gold"]["different"] == 1
    assert "two" not in json.dumps(report)
    assert report["input_fingerprint"]


def test_run_audit_uses_repository_validator_for_valid_and_mismatched_inputs():
    repository = FakeRepository(
        [
            Input(
                "yc",
                "1",
                {"id": 1, "slug": "valid-company", "one_liner": "Valid"},
            ),
            Input(
                "yc",
                "2",
                {"id": 3, "slug": "wrong-company", "one_liner": "Mismatch"},
            ),
        ]
    )

    report = run_audit("yc", repository)

    assert report["outcomes"] == {"captured": 1, "excluded": 0, "failed": 1}
    assert report["failure_reasons"] == {
        "normalized stable ID does not match Bronze stable ID": 1
    }


def test_run_audit_limit_is_deterministic_and_details_are_opt_in(tmp_path: Path):
    repo = FakeRepository(
        [
            Input("yc", "b", {"id": "b", "text": "B"}),
            Input("yc", "a", {"id": "a", "text": "A"}),
        ]
    )
    detail_path = tmp_path / "details.json"

    report = run_audit(
        "yc",
        repo,
        limit=1,
        normalizer=_normalize,
        details_path=detail_path,
        report_writer=FilesystemJsonReportWriter(),
    )

    assert report["input_count"] == 1
    assert report["available_input_count"] == 2
    assert report["selection"]["method"] == "md5(stable_id), stable_id"
    detail = json.loads(detail_path.read_text())
    assert len(detail["records"]) == 1
    assert detail["records"][0]["normalized_text"] in {"A", "B"}
    assert "downstream" in detail["records"][0]


def test_identical_payload_fingerprint_ignores_fetch_check_metadata():
    first = FakeRepository([Input("yc", "1", {"id": 1, "text": "same"})])
    second = FakeRepository(
        [
            Input(
                "yc",
                "1",
                {"id": 1, "text": "same"},
                last_checked_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        ]
    )

    first_report = run_audit("yc", first, normalizer=_normalize)
    second_report = run_audit("yc", second, normalizer=_normalize)

    assert first_report["input_fingerprint"] == second_report["input_fingerprint"]


def test_run_capture_persists_only_explicitly_and_preserves_each_outcome():
    repo = FakeRepository(
        [
            Input("yc", "1", {"id": 1, "text": "ok"}),
            Input("yc", "2", {"id": 2, "outcome": "excluded"}),
        ]
    )

    result = run_capture(
        "yc", repo, normalizer=_normalize, run_factory=lambda **kwargs: kwargs
    )

    assert repo.read_calls == [("yc", None, True)]
    assert repo.persisted["mode"] == "capture"
    assert [record["extraction"].status for record in repo.persisted["records"]] == [
        "captured",
        "excluded",
    ]
    assert result["persistence"]["status"] == "succeeded"


def test_run_capture_does_not_persist_when_summary_coverage_fails():
    class CoverageFailureRepository(FakeRepository):
        def __init__(self) -> None:
            super().__init__([Input("yc", "1", {"id": 1, "text": "ok"})])
            self.persist_calls = 0

        def coverage_counts(self, source: str) -> dict[str, int]:
            raise RuntimeError("coverage query failed")

        def persist_run(self, run):
            self.persist_calls += 1
            return super().persist_run(run)

    repository = CoverageFailureRepository()

    with pytest.raises(RuntimeError, match="coverage query failed"):
        run_capture(
            "yc",
            repository,
            normalizer=_normalize,
            run_factory=lambda **kwargs: kwargs,
        )

    assert repository.persist_calls == 0


def test_yc_report_counts_paired_descriptions_and_source_state_distinctions():
    repository = FakeRepository(
        [
            Input(
                "yc",
                "2",
                {
                    "id": 2,
                    "slug": "sample-co",
                    "one_liner": "Short pitch",
                    "long_description": "Long narrative",
                    "status": "Acquired",
                    "team_size": 0,
                    "isHiring": False,
                    "tags": ["B2B"],
                    "regions": ["North America"],
                },
            )
        ]
    )

    report = run_audit("yc", repository)

    metrics = report["source_metrics"]
    assert metrics["both_descriptions"] == 1
    assert metrics["hiring_false"] == 1
    assert metrics["hiring_unknown"] == 0
    assert metrics["team_size_zero"] == 1
    assert metrics["status_known"] == 1
    assert metrics["inactive_or_acquired_status"] == 1
    assert metrics["unprojected_source_fields"]["tags"] == 1
    assert metrics["unprojected_source_fields"]["regions"] == 1


def test_eu_report_counts_short_long_and_unprojected_source_fields():
    repository = FakeRepository(
        [Input("eu_startups", "brightroom", {"id": "brightroom"})]
    )

    def normalize(_payload: dict[str, object]) -> SourceExtraction:
        return SourceExtraction(
            source="eu_startups",
            stable_id="brightroom",
            status="captured",
            normalized_text="Short\nLong",
            source_fields={
                "short_description": "Short",
                "long_description": "Long",
                "category": "Germany",
                "place": "Berlin",
                "tags": "coaching, marketplace",
            },
            source_times={"lastmod": "2026-09-01T07:37:16+00:00"},
        )

    report = run_audit("eu_startups", repository, normalizer=normalize)

    metrics = report["source_metrics"]
    assert metrics["short_description"] == 1
    assert metrics["long_description"] == 1
    assert metrics["unprojected_source_fields"] == {
        "long_description": 1,
        "category": 1,
        "place": 1,
        "tags": 1,
    }
    assert metrics["source_time_fields"] == {"lastmod": 1}


def test_hn_report_identifies_full_time_header_context_missing_from_staging():
    repository = FakeRepository([Input("hn", "2", {"id": 2})])

    def normalize(_payload: dict[str, object]) -> SourceExtraction:
        text = "Remote | Full-time role\nTechnical work"
        return SourceExtraction(
            source="hn",
            stable_id="2",
            status="captured",
            normalized_text=text,
            header_span=(0, len("Remote | Full-time role")),
            body_span=(len("Remote | Full-time role") + 1, len(text)),
        )

    report = run_audit("hn", repository, normalizer=normalize)

    assert report["comparisons"]["hn_header_retention"] == {
        "header_span_records": 1,
        "full_time_phrase_in_header": 1,
        "full_time_phrase_missing_from_staging": 1,
        "example_stable_ids": ["2"],
        "full_time_header_context_missing_from_staging": 1,
        "header_context_example_stable_ids": ["2"],
    }


def test_hn_retention_metric_accepts_phrase_when_other_header_text_differs():
    repository = FakeRepository([Input("hn", "2", {"id": 2})])
    repository.read_audit_snapshot = lambda source, limit=None: type(
        "Snapshot",
        (),
        {
            "inputs": tuple(repository.inputs),
            "available_count": 1,
            "coverage_counts": {"bronze": 1},
            "downstream_by_stable_id": {
                "2": {"silver_staging_description": "Hiring FULL TIME engineers"}
            },
        },
    )()

    def normalize(_payload: dict[str, object]) -> SourceExtraction:
        text = "Remote | Full-time role\nTechnical work"
        return SourceExtraction(
            source="hn",
            stable_id="2",
            status="captured",
            normalized_text=text,
            header_span=(0, len("Remote | Full-time role")),
            body_span=(len("Remote | Full-time role") + 1, len(text)),
        )

    report = run_audit("hn", repository, normalizer=normalize)

    assert (
        report["comparisons"]["hn_header_retention"][
            "full_time_phrase_missing_from_staging"
        ]
        == 0
    )
    assert (
        report["comparisons"]["hn_header_retention"][
            "full_time_header_context_missing_from_staging"
        ]
        == 1
    )


def test_audit_and_capture_report_bronze_id_mismatches_as_failed(tmp_path: Path):
    for extraction_source, extraction_id, reason in (
        ("yc", "2", "normalized stable ID does not match Bronze stable ID"),
        ("hn", "1", "normalized source does not match run source"),
    ):
        repository = FakeRepository([Input("yc", "1", {"id": 1})])

        def normalize(
            _payload: dict[str, object],
            source: str = extraction_source,
            stable_id: str = extraction_id,
        ) -> SourceExtraction:
            return SourceExtraction(
                source=source,  # type: ignore[arg-type]
                stable_id=stable_id,
                status="captured",
                normalized_text="Mismatched record",
            )

        details_path = tmp_path / f"{extraction_source}-details.json"
        audited = run_audit(
            "yc",
            repository,
            normalizer=normalize,
            details_path=details_path,
            report_writer=FilesystemJsonReportWriter(),
        )
        captured = run_capture(
            "yc", repository, normalizer=normalize, run_factory=lambda **kwargs: kwargs
        )

        assert audited["outcomes"] == {"captured": 0, "excluded": 0, "failed": 1}
        assert audited["failure_reasons"] == {reason: 1}
        assert json.loads(details_path.read_text())["records"][0]["status"] == "failed"
        assert json.loads(details_path.read_text())["records"][0]["reason"] == reason
        assert captured["outcomes"] == audited["outcomes"]
        assert repository.persisted["records"][0]["extraction"].status == "failed"
