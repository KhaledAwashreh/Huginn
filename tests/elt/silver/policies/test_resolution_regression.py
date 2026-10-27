from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime

import pytest

from huginn.elt.silver.errors.resolution_regression import ResolutionRegressionError
from huginn.elt.silver.models.resolution_identity import ResolutionIdentity
from huginn.elt.silver.models.resolution_regression import ResolutionRegression
from huginn.elt.silver.models.resolved_signal_record import ResolvedSignalRecord
from huginn.elt.silver.policies.resolution_regression import check_resolution_regression


def _previous(count):
    return [
        ResolutionIdentity("yc", str(i), f"company-{i}.example") for i in range(count)
    ]


def _candidate(stable_id, derivation="domain_normalized"):
    return ResolvedSignalRecord(
        source="yc",
        source_stable_id=stable_id,
        resolved_company_key="new.example",
        company_name_raw="Company",
        signal_type="company_listing",
        stage=None,
        description=None,
        occurred_on=datetime(2026, 10, 25, tzinfo=UTC),
        url="https://example.test/listing",
        key_derivation=derivation,
    )


def test_exact_threshold_is_allowed_and_domain_changes_are_preserved():
    proposed = [_candidate(str(i)) for i in range(10)]
    proposed[0] = replace(proposed[0], key_derivation="unresolved")
    assert check_resolution_regression(_previous(10), proposed) == ResolutionRegression(
        10, 1, 10
    )


def test_above_threshold_raises_typed_error_with_report_and_safe_action():
    proposed = [_candidate(str(i), "unresolved") for i in range(2)]
    with pytest.raises(ResolutionRegressionError) as caught:
        check_resolution_regression(_previous(10), proposed)
    assert caught.value.regression == ResolutionRegression(2, 2, 10, source="yc")
    assert isinstance(caught.value, RuntimeError)
    assert "2" in str(caught.value)
    assert "10%" in str(caught.value)
    assert "review" in str(caught.value).lower()
    assert "example" not in str(caught.value)


def test_out_of_batch_previous_rows_are_not_counted_or_inferred_deleted():
    assert check_resolution_regression(
        _previous(100), [_candidate("0")]
    ) == ResolutionRegression(1, 0, 10)


def test_sources_are_part_of_the_identity():
    proposed = [replace(_candidate("0", "unresolved"), source="hn")]
    assert check_resolution_regression(_previous(1), proposed) == ResolutionRegression(
        0, 0, 10
    )


@pytest.mark.parametrize(
    "previous,proposed",
    [([], []), ([], [_candidate("new", "unresolved")]), (_previous(1), [])],
)
def test_no_prior_cohort_accepts_batch(previous, proposed):
    assert check_resolution_regression(previous, proposed) == ResolutionRegression(
        0, 0, 10
    )


@pytest.mark.parametrize(
    "derivation", ["unresolved", "fuzzy_matched", "", "DOMAIN_NORMALIZED"]
)
def test_every_non_domain_derivation_is_a_downgrade(derivation):
    with pytest.raises(ResolutionRegressionError):
        check_resolution_regression(_previous(1), [_candidate("0", derivation)])


def test_iterators_and_fractional_threshold_use_exact_arithmetic():
    proposed = (
        _candidate(str(i), "unresolved" if i == 0 else "domain_normalized")
        for i in range(11)
    )
    assert check_resolution_regression(
        iter(_previous(11)), proposed
    ) == ResolutionRegression(11, 1, 10)


@pytest.mark.parametrize("threshold", [True, False, -1, 101, 10.0, "10", None])
def test_invalid_threshold_is_rejected(threshold):
    with pytest.raises(ValueError, match="integer.*0.*100"):
        check_resolution_regression([], [], max_downgrade_percent=threshold)


def test_threshold_endpoints():
    with pytest.raises(ResolutionRegressionError):
        check_resolution_regression(
            _previous(1), [_candidate("0", "unresolved")], max_downgrade_percent=0
        )
    assert check_resolution_regression(
        _previous(1), [_candidate("0", "unresolved")], max_downgrade_percent=100
    ) == ResolutionRegression(1, 1, 100)


@pytest.mark.parametrize("duplicate_side", ["previous", "proposed"])
def test_duplicate_input_identities_are_rejected_even_without_overlap(duplicate_side):
    previous = _previous(1)
    proposed = [_candidate("other")]
    if duplicate_side == "previous":
        previous *= 2
    else:
        proposed *= 2
    with pytest.raises(ValueError, match="[Dd]uplicate"):
        check_resolution_regression(previous, proposed)


def test_same_native_id_across_sources_is_not_a_duplicate():
    previous = _previous(1)
    previous.append(replace(previous[0], source="hn"))
    proposed = [_candidate("0"), replace(_candidate("0"), source="hn")]
    assert check_resolution_regression(previous, proposed) == ResolutionRegression(
        2, 0, 10
    )


def test_report_and_identity_are_immutable_values():
    identity = _previous(1)[0]
    with pytest.raises(FrozenInstanceError):
        identity.resolved_company_key = "changed.example"
    report = ResolutionRegression(10, 1, 10)
    with pytest.raises(FrozenInstanceError):
        report.downgraded = 2


def test_large_healthy_source_cannot_mask_complete_loss_of_small_source():
    previous = _previous(4000) + [
        ResolutionIdentity("eu_startups", "small", "small.example")
    ]
    proposed = [_candidate(str(i)) for i in range(4000)]
    proposed.append(replace(_candidate("small", "unresolved"), source="eu_startups"))
    with pytest.raises(ResolutionRegressionError) as caught:
        check_resolution_regression(previous, proposed)
    assert caught.value.regression == ResolutionRegression(
        1, 1, 10, source="eu_startups"
    )
    assert "eu_startups" in str(caught.value)
    assert "small" not in str(caught.value)
    assert "example" not in str(caught.value)


def test_all_healthy_source_cohorts_return_aggregate_report():
    previous = _previous(4000) + [
        ResolutionIdentity("eu_startups", str(i), "eu.example") for i in range(20)
    ]
    proposed = [
        _candidate(str(i), "unresolved" if i < 4 else "domain_normalized")
        for i in range(4000)
    ]
    proposed += [
        replace(
            _candidate(str(i), "unresolved" if i == 0 else "domain_normalized"),
            source="eu_startups",
        )
        for i in range(20)
    ]
    assert check_resolution_regression(previous, proposed) == ResolutionRegression(
        4020, 5, 10
    )


def test_blocked_source_is_deterministic_regardless_of_input_order():
    previous = [
        ResolutionIdentity(source, "0", "old.example")
        for source in ("yc", "eu_startups")
    ]
    proposed = [
        replace(_candidate("0", "unresolved"), source=source)
        for source in ("yc", "eu_startups")
    ]
    for batch in (proposed, list(reversed(proposed))):
        with pytest.raises(ResolutionRegressionError) as caught:
            check_resolution_regression(iter(previous), iter(batch))
        assert caught.value.regression == ResolutionRegression(
            1, 1, 10, source="eu_startups"
        )


def test_source_without_prior_cohort_does_not_affect_other_source_counts():
    proposed = [
        _candidate("0"),
        replace(_candidate("new", "unresolved"), source="eu_startups"),
    ]
    assert check_resolution_regression(_previous(1), proposed) == ResolutionRegression(
        1, 0, 10
    )
