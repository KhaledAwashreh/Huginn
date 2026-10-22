"""Lifecycle audit and reconciliation orchestration; see architecture §4.2(5)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from pathlib import Path
from typing import cast

from huginn.elt.silver.context.models import SourceName
from huginn.elt.silver.context.runner import PARSER_VERSIONS
from huginn.elt.silver.currentness.models import (
    POLICY_VERSION,
    LifecycleFacts,
    LifecycleInput,
    ReconcileResult,
)
from huginn.elt.silver.currentness.ports import LifecycleRepository

logger = logging.getLogger(__name__)

Classifier = Callable[[LifecycleInput], LifecycleFacts]
Reconciler = Callable[[LifecycleInput, LifecycleFacts], ReconcileResult]


def _default_classifier() -> Classifier:
    from huginn.elt.silver.currentness.policy import classify

    return classify


def _fingerprint(items: Sequence[LifecycleInput]) -> str:
    signatures = [
        {
            "source": item.source,
            "stable_id": item.stable_id,
            "raw_token": item.raw_token,
            "resolution_token": item.resolution_token,
            "company_id": None if item.company_id is None else str(item.company_id),
        }
        for item in sorted(items, key=lambda value: (value.source, value.stable_id))
    ]
    encoded = json.dumps(
        signatures,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _prepare_summary_path(path: str | Path | None) -> Path | None:
    if path is None:
        return None
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not target.is_file():
        raise IsADirectoryError("summary path must name a file")
    if target.exists() and not os.access(target, os.W_OK):
        raise PermissionError("summary path is not writable")
    descriptor, probe = tempfile.mkstemp(prefix=".currentness-", dir=target.parent)
    os.close(descriptor)
    Path(probe).unlink()
    return target


def _write_summary(path: Path | None, report: Mapping[str, object]) -> None:
    if path is None:
        return
    descriptor, temporary = tempfile.mkstemp(prefix=".currentness-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(report, output, indent=2, ensure_ascii=False)
            output.write("\n")
        os.replace(temporary, path)
    except BaseException:
        with suppress(OSError):
            os.unlink(temporary)
        raise


def _base_report(
    mode: str,
    source: SourceName,
    items: Sequence[LifecycleInput],
    limit: int | None,
) -> dict[str, object]:
    return {
        "mode": mode,
        "source": source,
        "policy_version": POLICY_VERSION,
        "context_version": PARSER_VERSIONS[source],
        "status": "complete",
        "input_fingerprint": _fingerprint(items),
        "selection": {
            "limit": limit,
            "scope": "limited_sample" if limit is not None else "all_stored_inputs",
        },
        "selected_count": len(items),
        "classified_count": 0,
        "completed_count": 0,
        "states": {"listing": {}, "hiring": {}, "identity": {}},
        "reasons": {},
        "invalid_listing_count": 0,
        "invalid_or_unknown_count": 0,
    }


def _record_facts(report: dict[str, object], facts: LifecycleFacts) -> None:
    states = cast(dict[str, dict[str, int]], report["states"])
    for dimension, value in (
        ("listing", facts.listing_state),
        ("hiring", facts.hiring_state),
        ("identity", facts.identity_state),
    ):
        counts = states[dimension]
        counts[value] = counts.get(value, 0) + 1
    reasons = cast(dict[str, int], report["reasons"])
    reasons[facts.reason] = reasons.get(facts.reason, 0) + 1
    if facts.listing_state in ("invalid", "unknown"):
        report["invalid_or_unknown_count"] = (
            cast(int, report["invalid_or_unknown_count"]) + 1
        )
    if facts.listing_state == "invalid":
        report["invalid_listing_count"] = cast(int, report["invalid_listing_count"]) + 1


def _selected(
    source: SourceName, repository: LifecycleRepository, limit: int | None
) -> tuple[LifecycleInput, ...]:
    return repository.read_inputs(source, limit)


def run_audit(
    source: SourceName,
    repository: LifecycleRepository,
    *,
    limit: int | None = None,
    classifier: Classifier | None = None,
    summary_path: str | Path | None = None,
) -> dict[str, object]:
    """Classify a stored source snapshot and return aggregate-only output."""
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive")
    logger.info("Source currentness audit started source=%s limit=%s", source, limit)
    target = _prepare_summary_path(summary_path)
    items = _selected(source, repository, limit)
    report = _base_report("audit", source, items, limit)
    classify = classifier or _default_classifier()
    try:
        for item in items:
            _record_facts(report, classify(item))
            report["classified_count"] = cast(int, report["classified_count"]) + 1
            report["completed_count"] = cast(int, report["completed_count"]) + 1
    except KeyboardInterrupt:
        report["status"] = "partial"
        report["error_type"] = "KeyboardInterrupt"
    except Exception as error:
        report["status"] = "partial"
        report["error_type"] = type(error).__name__
    if cast(int, report["invalid_listing_count"]) > 0:
        report["status"] = "partial"
    _write_summary(target, report)
    logger.info(
        "Source currentness audit finished status=%s selected=%d classified=%d states=%s reasons=%s",
        report["status"],
        report["selected_count"],
        report["classified_count"],
        report["states"],
        report["reasons"],
    )
    return report


def run_reconcile(
    source: SourceName,
    repository: LifecycleRepository,
    *,
    limit: int | None = None,
    classifier: Classifier | None = None,
    reconcile: Reconciler | None = None,
    summary_path: str | Path | None = None,
) -> dict[str, object]:
    """Classify and persist per-input lifecycle observations."""
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive")
    logger.info(
        "Source currentness reconcile started source=%s limit=%s", source, limit
    )
    target = _prepare_summary_path(summary_path)
    items = _selected(source, repository, limit)
    report = _base_report("reconcile", source, items, limit)
    report["reconcile_counts"] = {"created": 0, "unchanged": 0, "stale": 0}
    classify = classifier or _default_classifier()
    write_observation = reconcile or repository.reconcile
    try:
        for item in items:
            facts = classify(item)
            _record_facts(report, facts)
            report["classified_count"] = cast(int, report["classified_count"]) + 1
            result = write_observation(item, facts)
            counts = cast(dict[str, int], report["reconcile_counts"])
            counts[result.status] += 1
            report["completed_count"] = cast(int, report["completed_count"]) + 1
            if result.status == "stale":
                report["status"] = "partial"
    except KeyboardInterrupt:
        report["status"] = "partial"
        report["error_type"] = "KeyboardInterrupt"
    except Exception as error:
        report["status"] = "partial"
        report["error_type"] = type(error).__name__
    if cast(int, report["invalid_listing_count"]) > 0:
        report["status"] = "partial"
    _write_summary(target, report)
    logger.info(
        "Source currentness reconcile finished status=%s selected=%d completed=%d classified=%d results=%s",
        report["status"],
        report["selected_count"],
        report["completed_count"],
        report["classified_count"],
        report["reconcile_counts"],
    )
    return report
