"""Orchestration and safe reporting for source-context audits and capture."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Protocol, cast
from uuid import UUID

from huginn.elt.silver.context.models import SourceExtraction, SourceName

PARSER_VERSIONS: dict[str, str] = {
    "hn": "hn-context-v1",
    "eu_startups": "eu-startups-context-v1",
    "yc": "yc-context-v1",
}
_SELECTION_METHOD = "md5(stable_id), stable_id"


class InputsRepository(Protocol):
    def read_inputs(
        self, source: SourceName, limit: int | None = None, *, read_only: bool = True
    ) -> list[object]: ...

    def count_inputs(self, source: SourceName) -> int: ...

    def coverage_counts(self, source: SourceName) -> dict[str, int]: ...

    def read_audit_snapshot(
        self, source: SourceName, limit: int | None = None
    ) -> object: ...

    def persist_run(self, run: object) -> object: ...


class AuditSnapshot(Protocol):
    inputs: Sequence[object]
    available_count: int
    coverage_counts: dict[str, int]
    downstream_by_stable_id: Mapping[str, Mapping[str, object]]


Normalizer = Callable[[dict[str, object]], SourceExtraction]


def _normalizers() -> dict[str, Normalizer]:
    from huginn.elt.silver.context.eu_startups import normalize_eu_startups
    from huginn.elt.silver.context.hn import normalize_hn
    from huginn.elt.silver.context.yc import normalize_yc

    return {
        "hn": normalize_hn,
        "eu_startups": normalize_eu_startups,
        "yc": normalize_yc,
    }


def _validated_extraction(
    source: str, stable_id: str, extraction: SourceExtraction
) -> SourceExtraction:
    from dataclasses import replace

    from huginn.elt.silver.context.repository import validate_record

    status, reason = validate_record(cast(SourceName, source), stable_id, extraction)
    if status == extraction.status and reason == extraction.reason:
        return extraction
    return replace(extraction, status=status, reason=reason)


def _input_value(item: object, name: str, default: object = None) -> object:
    if isinstance(item, Mapping):
        return item.get(name, default)
    return getattr(item, name, default)


def _input_payload(item: object) -> dict[str, object]:
    value = _input_value(item, "payload")
    if not isinstance(value, dict):
        raise TypeError("source context reader returned an invalid payload")
    return value


def _input_id(item: object) -> str:
    value = _input_value(item, "stable_id")
    if not isinstance(value, str) or not value:
        raise TypeError("source context reader returned an invalid stable ID")
    return value


def _select(items: Sequence[object], limit: int | None) -> list[object]:
    ordered = sorted(
        items,
        key=lambda item: (
            hashlib.md5(_input_id(item).encode()).hexdigest(),
            _input_id(item),
        ),
    )
    return ordered if limit is None else ordered[:limit]


def _canonical_fingerprint(items: Sequence[object]) -> str:
    payloads = [
        {"stable_id": _input_id(item), "payload": _input_payload(item)}
        for item in sorted(items, key=_input_id)
    ]
    canonical = json.dumps(
        payloads,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _code_version() -> str:
    try:
        return version("huginn")
    except PackageNotFoundError:
        return "unknown"


def _json_default(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"unsupported report value: {type(value).__name__}")


def _write_json(path: str | Path, value: object) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, default=_json_default) + "\n",
        encoding="utf-8",
    )


def _extraction_detail(extraction: SourceExtraction) -> dict[str, object]:
    return {
        "source": extraction.source,
        "stable_id": extraction.stable_id,
        "status": extraction.status,
        "reason": extraction.reason,
        "source_url": extraction.source_url,
        "normalized_text": extraction.normalized_text,
        "header_span": extraction.header_span,
        "body_span": extraction.body_span,
        "source_fields": extraction.source_fields,
        "source_times": extraction.source_times,
    }


def _field_coverage(
    extractions: Sequence[SourceExtraction],
) -> dict[str, dict[str, int]]:
    present: Counter[str] = Counter()
    known: Counter[str] = Counter()
    for extraction in extractions:
        if extraction.status == "captured":
            for key, value in extraction.source_fields.items():
                present[key] += 1
                if value is not None and value != "":
                    known[key] += 1
    return {
        key: {"present": present[key], "known": known[key]} for key in sorted(present)
    }


def _source_metrics(
    source: str, extractions: Sequence[SourceExtraction]
) -> dict[str, object]:
    captured = [item for item in extractions if item.status == "captured"]
    metrics: dict[str, object] = {
        "normalized_text_records": sum(
            item.normalized_text is not None for item in captured
        ),
        "source_time_fields": dict(
            sorted(
                Counter(key for item in captured for key in item.source_times).items()
            )
        ),
        "header_span_records": sum(item.header_span is not None for item in captured),
        "body_span_records": sum(item.body_span is not None for item in captured),
        "header_characters": sum(
            item.header_span[1] - item.header_span[0]
            for item in captured
            if item.header_span is not None
        ),
        "body_characters": sum(
            item.body_span[1] - item.body_span[0]
            for item in captured
            if item.body_span is not None
        ),
    }
    if source == "yc":
        fields = [item.source_fields for item in captured]
        short_present = [
            isinstance(value.get("one_liner"), str) and bool(value.get("one_liner"))
            for value in fields
        ]
        long_present = [
            isinstance(value.get("long_description"), str)
            and bool(value.get("long_description"))
            for value in fields
        ]
        metrics["one_liner"] = sum(short_present)
        metrics["long_description"] = sum(long_present)
        metrics["both_descriptions"] = sum(
            short and long
            for short, long in zip(short_present, long_present, strict=True)
        )
        metrics["one_liner_only"] = sum(
            short and not long
            for short, long in zip(short_present, long_present, strict=True)
        )
        metrics["long_description_only"] = sum(
            long and not short
            for short, long in zip(short_present, long_present, strict=True)
        )
        metrics["hiring_true"] = sum(value.get("isHiring") is True for value in fields)
        metrics["hiring_false"] = sum(
            value.get("isHiring") is False for value in fields
        )
        metrics["hiring_unknown"] = sum(
            value.get("isHiring") is None for value in fields
        )
        metrics["team_size_zero"] = sum(
            isinstance(value.get("team_size"), int)
            and not isinstance(value.get("team_size"), bool)
            and value.get("team_size") == 0
            for value in fields
        )
        metrics["status_known"] = sum(
            isinstance(value.get("status"), str) and bool(value.get("status"))
            for value in fields
        )
        metrics["status_unknown"] = sum(value.get("status") is None for value in fields)
        metrics["inactive_or_acquired_status"] = sum(
            value.get("status") in {"Inactive", "Acquired"} for value in fields
        )
        metrics["unprojected_source_fields"] = {
            field: sum(
                field in value and value[field] is not None and value[field] != ""
                for value in fields
            )
            for field in (
                "one_liner",
                "tags",
                "tags_highlighted",
                "regions",
                "industry",
                "subindustry",
                "isHiring",
            )
        }
    elif source == "eu_startups":
        fields = [item.source_fields for item in captured]
        metrics["short_description"] = sum(
            isinstance(value.get("short_description"), str) for value in fields
        )
        metrics["long_description"] = sum(
            isinstance(value.get("long_description"), str) for value in fields
        )
        metrics["unprojected_source_fields"] = {
            field: sum(
                field in value and value[field] is not None and value[field] != ""
                for value in fields
            )
            for field in ("long_description", "category", "place", "tags")
        }
    return metrics


def _coverage(
    repository: object,
    source: SourceName,
    selected_count: int,
    raw_counts: Mapping[str, int] | None = None,
) -> dict[str, int | None]:
    if raw_counts is None:
        method = getattr(repository, "coverage_counts", None)
        raw = method(source) if callable(method) else {}
    else:
        raw = raw_counts
    if not isinstance(raw, Mapping):
        raw = {}
    linked = raw.get("resolved_linked", raw.get("silver_resolved"))
    unresolved = raw.get("unresolved_signals", raw.get("silver_unresolved"))
    total_resolved = raw.get("resolved_signals")
    if (
        total_resolved is None
        and isinstance(linked, int)
        and isinstance(unresolved, int)
    ):
        total_resolved = linked + unresolved
    return {
        "bronze": cast(int | None, raw.get("bronze", selected_count)),
        "source_staging": cast(
            int | None, raw.get("source_staging", raw.get("silver_staging"))
        ),
        "resolved_signals": cast(int | None, total_resolved),
        "resolved_linked_signals": cast(int | None, linked),
        "unresolved_signals": cast(int | None, unresolved),
        "gold": cast(int | None, raw.get("gold", raw.get("gold_signals"))),
    }


def _comparisons(
    source: str,
    selected: Sequence[object],
    extractions: Sequence[SourceExtraction],
    downstream_by_stable_id: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    layers = {
        "silver_staging": "silver_staging_description",
        "silver_resolved": "silver_resolved_description",
        "gold": "gold_description",
    }
    counts: dict[str, object] = {}
    for layer, field in layers.items():
        compared = different = missing = 0
        examples: list[str] = []
        for item, extraction in zip(selected, extractions, strict=True):
            downstream = downstream_by_stable_id.get(_input_id(item), {})
            previous = downstream.get(field)
            if source == "yc":
                source_fields = extraction.source_fields
                current = source_fields.get("long_description") or source_fields.get(
                    "one_liner"
                )
            elif source == "eu_startups":
                current = extraction.source_fields.get("short_description")
            else:
                current = extraction.normalized_text
            if not isinstance(current, str):
                continue
            if current is None or extraction.status != "captured":
                continue
            if previous is None:
                missing += 1
                if len(examples) < 5:
                    examples.append(_input_id(item))
            elif isinstance(previous, str):
                compared += 1
                if previous != current:
                    different += 1
                    if len(examples) < 5:
                        examples.append(_input_id(item))
        counts[layer] = {
            "compared": compared,
            "different": different,
            "missing_downstream": missing,
            "example_stable_ids": examples,
        }
    if source == "hn":
        header_count = full_time_count = phrase_missing = header_context_missing = 0
        full_time_examples: list[str] = []
        header_context_examples: list[str] = []
        for item, extraction in zip(selected, extractions, strict=True):
            if extraction.status != "captured" or extraction.header_span is None:
                continue
            header_count += 1
            if extraction.normalized_text is None:
                continue
            start, end = extraction.header_span
            header = extraction.normalized_text[start:end]
            normalized_header = header.casefold()
            if (
                "full-time" not in normalized_header
                and "full time" not in normalized_header
            ):
                continue
            full_time_count += 1
            old_description = downstream_by_stable_id.get(_input_id(item), {}).get(
                "silver_staging_description"
            )
            if (
                not isinstance(old_description, str)
                or re.search(r"\bfull[- ]time\b", old_description, flags=re.IGNORECASE)
                is None
            ):
                phrase_missing += 1
                if len(full_time_examples) < 5:
                    full_time_examples.append(_input_id(item))
            normalized_header = " ".join(header.split()).casefold()
            normalized_previous = (
                " ".join(old_description.split()).casefold()
                if isinstance(old_description, str)
                else ""
            )
            if not normalized_header or normalized_header not in normalized_previous:
                header_context_missing += 1
                if len(header_context_examples) < 5:
                    header_context_examples.append(_input_id(item))
        counts["hn_header_retention"] = {
            "header_span_records": header_count,
            "full_time_phrase_in_header": full_time_count,
            "full_time_phrase_missing_from_staging": phrase_missing,
            "example_stable_ids": full_time_examples,
            "full_time_header_context_missing_from_staging": header_context_missing,
            "header_context_example_stable_ids": header_context_examples,
        }
    return counts


def _prepare(
    source: str,
    repository: InputsRepository,
    *,
    limit: int | None,
    normalizer: Normalizer | None,
    audit: bool = False,
) -> tuple[
    list[object],
    list[SourceExtraction],
    int,
    str,
    dict[str, int] | None,
    Mapping[str, Mapping[str, object]],
]:
    if source not in PARSER_VERSIONS:
        raise ValueError(f"unsupported source: {source}")
    reader = _normalizers()[source] if normalizer is None else normalizer
    raw_coverage: dict[str, int] | None = None
    downstream_by_stable_id: Mapping[str, Mapping[str, object]] = {}
    if audit and callable(getattr(repository, "read_audit_snapshot", None)):
        snapshot = cast(
            AuditSnapshot,
            repository.read_audit_snapshot(cast(SourceName, source), limit),
        )
        available_count = snapshot.available_count
        inputs = list(snapshot.inputs)
        raw_coverage = snapshot.coverage_counts
        downstream_by_stable_id = snapshot.downstream_by_stable_id
    else:
        available_count = repository.count_inputs(cast(SourceName, source))
        inputs = repository.read_inputs(cast(SourceName, source), limit, read_only=True)
    selected = _select(inputs, limit)
    extractions = [
        _validated_extraction(source, _input_id(item), reader(_input_payload(item)))
        for item in selected
    ]
    fingerprint = _canonical_fingerprint(selected)
    return (
        selected,
        extractions,
        available_count,
        fingerprint,
        raw_coverage,
        downstream_by_stable_id,
    )


def _summary(
    source: str,
    repository: InputsRepository,
    selected: Sequence[object],
    extractions: Sequence[SourceExtraction],
    available_count: int,
    fingerprint: str,
    limit: int | None,
    *,
    mode: str,
    raw_coverage: Mapping[str, int] | None = None,
    downstream_by_stable_id: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, object]:
    outcomes = Counter(item.status for item in extractions)
    return {
        "mode": mode,
        "source": source,
        "code_version": _code_version(),
        "parser_version": PARSER_VERSIONS[source],
        "audit_time": datetime.now(UTC).isoformat(),
        "input_fingerprint": fingerprint,
        "selection": {"method": _SELECTION_METHOD, "limit": limit},
        "available_input_count": available_count,
        "input_count": len(selected),
        "eligible_input_count": outcomes["captured"] + outcomes["failed"],
        "outcomes": {
            "captured": outcomes["captured"],
            "excluded": outcomes["excluded"],
            "failed": outcomes["failed"],
        },
        "failure_reasons": dict(
            sorted(
                Counter(
                    item.reason or "unspecified"
                    for item in extractions
                    if item.status == "failed"
                ).items()
            )
        ),
        "failure_ids": [
            _input_id(item)
            for item, extraction in zip(selected, extractions, strict=True)
            if extraction.status == "failed"
        ],
        "field_coverage": _field_coverage(extractions),
        "source_metrics": _source_metrics(source, extractions),
        "observation_metadata": {
            key: sum(_input_value(item, key) is not None for item in selected)
            for key in ("fetched_at", "last_checked_at")
        },
        "coverage": _coverage(
            repository,
            cast(SourceName, source),
            len(selected),
            raw_coverage,
        ),
        "comparisons": _comparisons(
            source,
            selected,
            extractions,
            downstream_by_stable_id or {},
        ),
        "signal_counts_are_unique_companies": False,
    }


def run_audit(
    source: str,
    repository: InputsRepository,
    *,
    limit: int | None = None,
    normalizer: Normalizer | None = None,
    details_path: str | Path | None = None,
    summary_path: str | Path | None = None,
) -> dict[str, object]:
    """Read, normalize, and report source rows without writing to the database."""
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive")
    (
        selected,
        extractions,
        available_count,
        fingerprint,
        raw_coverage,
        downstream_by_stable_id,
    ) = _prepare(source, repository, limit=limit, normalizer=normalizer, audit=True)
    report = _summary(
        source,
        repository,
        selected,
        extractions,
        available_count,
        fingerprint,
        limit,
        mode="audit",
        raw_coverage=raw_coverage,
        downstream_by_stable_id=downstream_by_stable_id,
    )
    if details_path is not None:
        _write_json(
            details_path,
            {
                "source": source,
                "input_fingerprint": fingerprint,
                "parser_version": PARSER_VERSIONS[source],
                "records": [
                    {
                        **_extraction_detail(extraction),
                        "observation": {
                            key: _input_value(item, key)
                            for key in ("fetched_at", "last_checked_at")
                            if _input_value(item, key) is not None
                        },
                        "downstream": downstream_by_stable_id.get(_input_id(item), {}),
                    }
                    for item, extraction in zip(selected, extractions, strict=True)
                ],
            },
        )
    if summary_path is not None:
        _write_json(summary_path, report)
    return report


def run_capture(
    source: str,
    repository: InputsRepository,
    *,
    limit: int | None = None,
    normalizer: Normalizer | None = None,
    run_factory: Callable[..., object] | None = None,
    summary_path: str | Path | None = None,
) -> dict[str, object]:
    """Normalize selected Bronze inputs and explicitly persist one context run."""
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive")
    selected, extractions, available_count, fingerprint, _, _ = _prepare(
        source, repository, limit=limit, normalizer=normalizer
    )
    if run_factory is None:
        from huginn.elt.silver.context.repository import ContextRecord, ContextRun

        def default_run_factory(**kwargs: object) -> object:
            raw_records = cast(Sequence[dict[str, object]], kwargs["records"])
            return ContextRun(
                source=cast(SourceName, kwargs["source"]),
                parser_version=cast(str, kwargs["parser_version"]),
                input_fingerprint=cast(str, kwargs["input_fingerprint"]),
                records=tuple(
                    ContextRecord(
                        stable_id=cast(str, record["stable_id"]),
                        payload=cast(dict[str, object], record["payload"]),
                        extraction=cast(SourceExtraction, record["extraction"]),
                        observation=cast(dict[str, object], record["observation"]),
                    )
                    for record in raw_records
                ),
                mode="capture",
            )

        run_factory = default_run_factory

    records = []
    for item, extraction in zip(selected, extractions, strict=True):
        records.append(
            {
                "stable_id": _input_id(item),
                "payload": _input_payload(item),
                "extraction": extraction,
                "observation": {
                    key: value
                    for key in ("fetched_at", "last_checked_at")
                    if (value := _input_value(item, key)) is not None
                },
            }
        )
    run = run_factory(
        source=source,
        parser_version=PARSER_VERSIONS[source],
        input_fingerprint=fingerprint,
        records=records,
        mode="capture",
    )
    persisted = repository.persist_run(run)
    report = _summary(
        source,
        repository,
        selected,
        extractions,
        available_count,
        fingerprint,
        limit,
        mode="capture",
    )
    if isinstance(persisted, Mapping):
        persistence = dict(persisted)
    else:
        persistence = {
            key: getattr(persisted, key)
            for key in (
                "run_id",
                "input_count",
                "captured_count",
                "excluded_count",
                "failed_count",
                "status",
            )
            if hasattr(persisted, key)
        }
    report["persistence"] = persistence
    if summary_path is not None:
        _write_json(summary_path, report)
    return report
