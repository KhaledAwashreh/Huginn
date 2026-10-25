"""Pure per-source batch regression guard; see ADR-0018."""

from collections.abc import Iterable

from huginn.elt.silver.errors.resolution_regression import ResolutionRegressionError
from huginn.elt.silver.models.resolution_identity import ResolutionIdentity
from huginn.elt.silver.models.resolution_regression import ResolutionRegression
from huginn.elt.silver.models.resolved_signal_record import ResolvedSignalRecord


def check_resolution_regression(
    previous: Iterable[ResolutionIdentity],
    proposed: Iterable[ResolvedSignalRecord],
    *,
    max_downgrade_percent: int = 10,
) -> ResolutionRegression:
    """Reject excessive per-source identity loss before writes; see ADR-0018."""
    if (
        isinstance(max_downgrade_percent, bool)
        or not isinstance(max_downgrade_percent, int)
        or not 0 <= max_downgrade_percent <= 100
    ):
        raise ValueError("max_downgrade_percent must be an integer from 0 to 100")

    previous_keys: set[tuple[str, str]] = set()
    for identity in previous:
        key = (identity.source, identity.source_stable_id)
        if key in previous_keys:
            raise ValueError("Duplicate identity in previous resolution batch")
        previous_keys.add(key)

    proposed_keys: set[tuple[str, str]] = set()
    previously_resolved = 0
    downgraded = 0
    counts_by_source: dict[str, tuple[int, int]] = {}
    for candidate in proposed:
        key = (candidate.source, candidate.source_stable_id)
        if key in proposed_keys:
            raise ValueError("Duplicate identity in proposed resolution batch")
        proposed_keys.add(key)
        if key in previous_keys:
            previously_resolved += 1
            is_downgrade = candidate.key_derivation != "domain_normalized"
            if is_downgrade:
                downgraded += 1
            source_previous, source_downgraded = counts_by_source.get(
                candidate.source, (0, 0)
            )
            counts_by_source[candidate.source] = (
                source_previous + 1,
                source_downgraded + int(is_downgrade),
            )

    regression = ResolutionRegression(
        previously_resolved=previously_resolved,
        downgraded=downgraded,
        max_downgrade_percent=max_downgrade_percent,
    )
    for source in sorted(counts_by_source):
        source_previous, source_downgraded = counts_by_source[source]
        if source_downgraded * 100 > source_previous * max_downgrade_percent:
            raise ResolutionRegressionError(
                ResolutionRegression(
                    previously_resolved=source_previous,
                    downgraded=source_downgraded,
                    max_downgrade_percent=max_downgrade_percent,
                    source=source,
                )
            )
    return regression
