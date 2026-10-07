from uuid import UUID

import pytest

from huginn.matchmaking.domain.errors.criteria import (
    CriteriaIssue,
    CriteriaIssueReason,
)
from huginn.matchmaking.domain.services.icp_evaluator import compile_icp
from huginn.matchmaking.domain.value_objects.compiled_criteria import CompiledCriteria


def criteria(**overrides):
    values = {
        "industries": ({"name": " SaaS "},),
        "company_sizes": ({"band": "0-10"},),
        "geographies": ({"kind": "country", "value": " Germany "},),
        "exclusions": (),
    }
    values.update(overrides)
    return compile_icp(**values)


@pytest.mark.parametrize(
    "field",
    ["industries", "company_sizes", "geographies"],
)
def test_any_empty_positive_dimension_is_incomplete_before_query(field):
    result = criteria(**{field: ()})

    assert result == CriteriaIssue(CriteriaIssueReason.INCOMPLETE_ICP)


def test_complete_criteria_are_flat_normalized_and_have_all_exclusions():
    result = criteria(
        industries=({"name": " SaaS "}, {"name": "Fintech"}, {"name": "SaaS"}),
        company_sizes=({"band": "11-100"}, {"band": "0-10"}),
        geographies=(
            {"kind": "country", "value": "Germany"},
            {"kind": "country", "value": "Netherlands"},
        ),
        exclusions=(
            {"kind": "company", "company_id": "00000000-0000-0000-0000-000000000002"},
            {"kind": "industry", "name": "Gambling"},
            {
                "kind": "geography",
                "geography": {"kind": "country", "value": "France"},
            },
        ),
    )

    assert result == CompiledCriteria(
        industries=("Fintech", "SaaS"),
        company_sizes=("0-10", "11-100"),
        countries=("Germany", "Netherlands"),
        excluded_company_ids=(UUID("00000000-0000-0000-0000-000000000002"),),
        excluded_industries=("Gambling",),
        excluded_countries=("France",),
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("industries", None),
        ("industries", [{"name": "SaaS"}]),
        ("industries", ({"name": "SaaS", "extra": True},)),
        ("industries", ({"name": " "},)),
        ("company_sizes", ({"band": "10-50"},)),
        ("company_sizes", ({"band": True},)),
        ("geographies", ({"kind": "region", "value": "Europe", "x": 1},)),
        ("geographies", ({"kind": "planet", "value": "Earth"},)),
        (
            "exclusions",
            ({"kind": "company", "company_id": "not-a-uuid"},),
        ),
        (
            "exclusions",
            ({"kind": "geography", "geography": {"kind": "region", "value": ""}},),
        ),
    ],
)
def test_any_malformed_item_or_outer_shape_is_invalid(field, value):
    result = criteria(**{field: value})

    assert result == CriteriaIssue(CriteriaIssueReason.INVALID_ICP)


def test_invalid_data_precedes_incompleteness_and_region_support():
    result = criteria(
        industries=(),
        geographies=({"kind": "region", "value": "Europe"},),
        exclusions=({"kind": "company", "company_id": "bad"},),
    )

    assert result == CriteriaIssue(CriteriaIssueReason.INVALID_ICP)


def test_incomplete_precedes_a_valid_region_criterion_or_exclusion():
    assert criteria(
        industries=(),
        geographies=({"kind": "region", "value": "Europe"},),
    ) == CriteriaIssue(CriteriaIssueReason.INCOMPLETE_ICP)
    assert criteria(
        industries=(),
        exclusions=(
            {"kind": "geography", "geography": {"kind": "region", "value": "Europe"}},
        ),
    ) == CriteriaIssue(CriteriaIssueReason.INCOMPLETE_ICP)


def test_regions_are_unsupported_after_every_item_is_validated():
    result = criteria(geographies=({"kind": "region", "value": "Europe"},))

    assert result == CriteriaIssue(CriteriaIssueReason.UNSUPPORTED_REGION)


def test_reserved_unspecified_industry_is_invalid_as_a_positive_target():
    assert criteria(industries=({"name": " Unspecified "},)) == CriteriaIssue(
        CriteriaIssueReason.INVALID_ICP
    )


def test_unspecified_exclusion_is_retained_for_sql_missing_value_filter():
    result = criteria(exclusions=({"kind": "industry", "name": " Unspecified "},))

    assert isinstance(result, CompiledCriteria)
    assert result.excluded_industries == ("Unspecified",)


def test_exact_trimmed_duplicates_are_removed_but_case_is_preserved():
    result = criteria(
        industries=({"name": " SaaS "}, {"name": "SaaS"}, {"name": "saas"})
    )

    assert isinstance(result, CompiledCriteria)
    assert result.industries == ("SaaS", "saas")
