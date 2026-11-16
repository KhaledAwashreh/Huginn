import pytest

from huginn.management.domain.value_objects.activity_kind import ActivityKind
from huginn.management.domain.value_objects.offer_cycle_status import OfferCycleStatus
from huginn.management.domain.value_objects.prospect_stage import ProspectStage


@pytest.mark.parametrize(
    ("value_type", "value"),
    [
        (ProspectStage, "in_conversation"),
        (ActivityKind, "proposal_sent"),
        (OfferCycleStatus, "unknown"),
    ],
)
def test_prospect_vocabulary_values_keep_string_construction_and_value_access(
    value_type, value
):
    instance = value_type(value)

    assert instance.value == value
    assert value_type(instance.value) == instance
    assert str(instance) == value


@pytest.mark.parametrize(
    ("value_type", "value"),
    [
        (ProspectStage, "invalid"),
        (ActivityKind, "invalid"),
        (OfferCycleStatus, "invalid"),
        (ProspectStage, 1),
        (ActivityKind, None),
        (OfferCycleStatus, []),
    ],
)
def test_prospect_vocabulary_values_reject_unknown_and_non_string_values(
    value_type, value
):
    with pytest.raises((TypeError, ValueError)):
        value_type(value)
