import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

from huginn.elt.gold.attribute_promotion.models import CompanyAttributes, SourceFact
from huginn.elt.gold.attribute_promotion.policy import MAPPING_VERSION, assess

COMPANY_ID = UUID("00000000-0000-0000-0000-000000000001")


def fact(
    source: str, token: str, *, raw: str | None = None, stable_id: str = "yc:1"
) -> SourceFact:
    return SourceFact(
        company_id=COMPANY_ID,
        source=source,
        stable_id=stable_id,
        observation_id=uuid5(NAMESPACE_URL, stable_id),
        snapshot_id=UUID("00000000-0000-0000-0000-000000000003"),
        raw_token=token if raw is None else raw,
        resolution_token=token,
        context_version="context-v1",
        policy_version="source-policy-v1",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        source_fields=(
            '{"industries":' + token + "}"
            if source == "yc" and token.startswith("[")
            else '{"team_size":'
            + (
                token
                if token in {"", "null", "true"}
                or token.lstrip("-").replace(".", "", 1).isdigit()
                else json.dumps(token)
            )
            + "}"
            if source == "yc"
            else "{}"
        ),
    )


def country_fact(
    source: str, fields: dict[str, object], *, stable_id: str
) -> SourceFact:
    return replace(
        fact(source, "country", stable_id=stable_id),
        source_fields=json.dumps(fields),
    )


def company(**changes: object) -> CompanyAttributes:
    values: dict[str, object] = {
        "company_id": COMPANY_ID,
        "business_sector": None,
        "company_scale": None,
        "country": None,
    }
    values.update(changes)
    return CompanyAttributes(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("team_size", "expected"),
    [
        (0, "0-10"),
        (10, "0-10"),
        (11, "11-100"),
        (100, "11-100"),
        (101, "101-1000"),
        (1000, "101-1000"),
        (1001, "1001+"),
    ],
)
def test_yc_team_size_uses_gold_band_boundaries(team_size: int, expected: str) -> None:
    proposals = assess(company(), [fact("yc", str(team_size))])
    scale = next(item for item in proposals if item.field_name == "company_scale")
    assert (scale.status, scale.proposed_value, scale.mapping_version) == (
        "proposed",
        expected,
        MAPPING_VERSION,
    )


@pytest.mark.parametrize("token", ["-1", "1.5", "ten", "true"])
def test_invalid_yc_team_size_is_explicit_and_does_not_fill(token: str) -> None:
    proposals = assess(company(), [fact("yc", token)])
    scale = next(item for item in proposals if item.field_name == "company_scale")
    assert scale.status == "invalid"
    assert scale.proposed_value is None


def test_yc_industries_preserve_labels_but_ignore_blank_and_unspecified() -> None:
    proposal = next(
        item
        for item in assess(
            company(), [fact("yc", '[" SaaS ", "Unspecified", "", "Biotech"]')]
        )
        if item.field_name == "business_sector"
    )
    assert proposal.proposed_value == ("Biotech", "SaaS")
    assert proposal.status == "proposed"


def test_explicit_empty_industries_remain_distinct_from_absence() -> None:
    proposal = next(
        item
        for item in assess(company(), [fact("yc", "[]")])
        if item.field_name == "business_sector"
    )
    assert proposal.status == "absent"
    assert proposal.old_value is None


@pytest.mark.parametrize(
    "fields", ['{"industries":"SaaS"}', '{"industries":{"name":"SaaS"}}', "not-json"]
)
def test_malformed_or_wrong_shape_industries_are_invalid(fields: str) -> None:
    proposal = next(
        item
        for item in assess(company(), [replace(fact("yc", "[]"), source_fields=fields)])
        if item.field_name == "business_sector"
    )
    assert proposal.status == "invalid"


def test_null_industries_are_absent_but_empty_list_is_absent() -> None:
    for fields in ('{"industries":null}', '{"industries":[]}'):
        proposal = next(
            item
            for item in assess(
                company(), [replace(fact("yc", "[]"), source_fields=fields)]
            )
            if item.field_name == "business_sector"
        )
        assert proposal.status == "absent"


@pytest.mark.parametrize("gold", [(), ("",), ("Unspecified",), ("  ",)])
def test_nonmeaningful_gold_sector_values_are_missing(gold: tuple[str, ...]) -> None:
    proposal = next(
        item
        for item in assess(company(business_sector=gold), [fact("yc", '["SaaS"]')])
        if item.field_name == "business_sector"
    )
    assert proposal.status == "proposed"
    assert proposal.proposed_value == ("SaaS",)


def test_null_gold_sector_array_entries_are_preserved_and_ignored_for_meaningfulness() -> (
    None
):
    proposal = next(
        item
        for item in assess(
            company(business_sector=(None, " ", "Unspecified")),
            [fact("yc", '["SaaS"]')],
        )
        if item.field_name == "business_sector"
    )
    assert proposal.old_value == (None, " ", "Unspecified")
    assert proposal.status == "proposed"


def test_gold_comparison_matches_lower_btrim_semantics_and_ignores_order() -> None:
    proposal = next(
        item
        for item in assess(
            company(business_sector=(" biotech ", "SAAS", "SaaS")),
            [fact("yc", '["SaaS", "Biotech"]')],
        )
        if item.field_name == "business_sector"
    )
    assert proposal.status == "unchanged"


def test_tab_only_gold_sector_and_country_are_present_under_sql_btrim() -> None:
    company_record = company(business_sector=("\t",), country="\t")
    proposals = assess(company_record, [fact("yc", '["SaaS"]')])
    assert (
        next(item for item in proposals if item.field_name == "business_sector").status
        == "conflict"
    )
    country = next(item for item in proposals if item.field_name == "country")
    assert country.status == "unchanged"
    assert country.old_value == "\t"


def test_yc_country_requires_one_explicit_allowlisted_location() -> None:
    proposal = next(
        item
        for item in assess(
            company(),
            [
                country_fact(
                    "yc", {"all_locations": "San Francisco, CA, USA"}, stable_id="yc"
                )
            ],
        )
        if item.field_name == "country"
    )
    assert proposal.status == "proposed"
    assert proposal.proposed_value == "USA"
    assert proposal.source_fields == ("yc.all_locations",)


@pytest.mark.parametrize(
    "location",
    [
        "London, United Kingdom; New York, USA",
        "London, United Kingdom; London, United Kingdom",
        "Remote",
        "Remote; London, United Kingdom",
        "Remote, USA",
        "San Francisco, Remote, USA",
        "London, UK",
        "London",
        "India",
        ", USA",
        "San Francisco, CA, California",
    ],
)
def test_yc_country_ambiguous_locations_abstain(location: str) -> None:
    proposal = next(
        item
        for item in assess(
            company(), [country_fact("yc", {"all_locations": location}, stable_id="yc")]
        )
        if item.field_name == "country"
    )
    assert proposal.status == "ambiguous"
    assert proposal.proposed_value is None


def test_yc_missing_and_invalid_country_location_are_distinguished() -> None:
    missing = next(
        item
        for item in assess(
            company(),
            [country_fact("yc", {"all_locations": None}, stable_id="missing")],
        )
        if item.field_name == "country"
    )
    invalid = next(
        item
        for item in assess(
            company(), [country_fact("yc", {"all_locations": 42}, stable_id="invalid")]
        )
        if item.field_name == "country"
    )
    assert missing.status == "absent"
    assert invalid.status == "invalid"


@pytest.mark.parametrize(
    ("category", "place", "expected"),
    [
        ("Germany", "Berlin, Germany", "Germany"),
        ("UK", "London, United Kingdom", "UK"),
        ("UK", "London, UK", "UK"),
    ],
)
def test_eu_country_requires_agreeing_explicit_category_and_place(
    category: str, place: str, expected: str
) -> None:
    proposal = next(
        item
        for item in assess(
            company(),
            [
                country_fact(
                    "eu_startups",
                    {"category": category, "place": place},
                    stable_id="eu",
                )
            ],
        )
        if item.field_name == "country"
    )
    assert proposal.status == "proposed"
    assert proposal.proposed_value == expected
    assert proposal.source_fields == ("eu_startups.category", "eu_startups.place")


@pytest.mark.parametrize(
    ("category", "place"),
    [("Cyprus", "Bronx"), ("Finland", "texas"), ("Spain", "Rajkot")],
)
def test_eu_country_city_only_place_does_not_corrobate_category(
    category: str, place: str
) -> None:
    proposal = next(
        item
        for item in assess(
            company(),
            [
                country_fact(
                    "eu_startups",
                    {"category": category, "place": place},
                    stable_id="eu",
                )
            ],
        )
        if item.field_name == "country"
    )
    assert proposal.status == "ambiguous"


def test_eu_disagreeing_explicit_category_and_place_are_conflict() -> None:
    proposal = next(
        item
        for item in assess(
            company(),
            [
                country_fact(
                    "eu_startups",
                    {"category": "Finland", "place": "Berlin, Germany"},
                    stable_id="eu",
                )
            ],
        )
        if item.field_name == "country"
    )
    assert proposal.status == "conflict"
    assert proposal.proposed_value is None


def test_eu_unobserved_category_is_ambiguous_even_if_place_names_same_country() -> None:
    proposal = next(
        item
        for item in assess(
            company(),
            [
                country_fact(
                    "eu_startups",
                    {"category": "United Kingdom", "place": "London, United Kingdom"},
                    stable_id="eu",
                )
            ],
        )
        if item.field_name == "country"
    )
    assert proposal.status == "ambiguous"


def test_country_facts_conflict_across_sources_including_known_aliases() -> None:
    conflict = next(
        item
        for item in assess(
            company(),
            [
                country_fact(
                    "yc", {"all_locations": "San Francisco, CA, USA"}, stable_id="yc"
                ),
                country_fact(
                    "eu_startups",
                    {"category": "Germany", "place": "Berlin, Germany"},
                    stable_id="eu",
                ),
            ],
        )
        if item.field_name == "country"
    )
    aliases = next(
        item
        for item in assess(
            company(),
            [
                country_fact(
                    "yc", {"all_locations": "New York, NY, USA"}, stable_id="yc"
                ),
                country_fact(
                    "yc",
                    {"all_locations": "New York, NY, United States"},
                    stable_id="yc2",
                ),
            ],
        )
        if item.field_name == "country"
    )
    assert conflict.status == "conflict"
    assert aliases.status == "conflict"
    assert aliases.proposed_value is None


@pytest.mark.parametrize("gold", ["", "   "])
def test_blank_gold_country_is_missing_even_though_country_mapping_abstains(
    gold: str,
) -> None:
    proposal = next(
        item
        for item in assess(company(country=gold), [fact("yc", "[]")])
        if item.field_name == "country"
    )
    assert proposal.status == "absent"
    assert proposal.old_value == gold


def test_existing_meaningful_value_conflicting_with_source_is_reported_and_preserved() -> (
    None
):
    proposal = next(
        item
        for item in assess(company(company_scale="0-10"), [fact("yc", "11")])
        if item.field_name == "company_scale"
    )
    assert proposal.status == "conflict"
    assert proposal.old_value == "0-10"
    assert proposal.proposed_value is None


def test_existing_meaningful_value_with_matching_and_conflicting_sources_is_conflict() -> (
    None
):
    proposal = next(
        item
        for item in assess(
            company(company_scale="0-10"),
            [fact("yc", "10"), fact("yc", "11", stable_id="b")],
        )
        if item.field_name == "company_scale"
    )
    assert proposal.status == "conflict"
    assert proposal.old_value == "0-10"
    assert proposal.proposed_value is None
    assert len(proposal.supporting_fact_ids) == 2


def test_invalid_and_agreeing_evidence_with_existing_value_is_invalid_with_full_lineage() -> (
    None
):
    proposal = next(
        item
        for item in assess(
            company(company_scale="0-10"),
            [fact("yc", "10"), fact("yc", "-1", stable_id="bad")],
        )
        if item.field_name == "company_scale"
    )
    assert proposal.status == "invalid"
    assert proposal.old_value == "0-10"
    assert proposal.proposed_value is None
    assert len(proposal.supporting_fact_ids) == 2


def test_city_only_country_evidence_is_ambiguous_without_claiming_disagreement():
    proposal = next(
        p
        for p in assess(
            company(country="Germany"),
            [
                country_fact(
                    "eu_startups",
                    {"category": "Germany", "place": "Berlin"},
                    stable_id="eu",
                )
            ],
        )
        if p.field_name == "country"
    )
    assert proposal.status == "ambiguous"
    assert proposal.old_value == "Germany"
    assert proposal.proposed_value is None


def test_other_sources_are_unsupported_for_sector_and_size_and_country_abstains() -> (
    None
):
    proposals = assess(company(), [fact("hn", "AI startup in USA")])
    by_field = {item.field_name: item for item in proposals}
    assert set(by_field) == {"business_sector", "company_scale", "country"}
    assert {item.status for item in by_field.values()} == {"unsupported"}
    assert all(item.proposed_value is None for item in by_field.values())


def test_country_is_never_guessed_from_yc_location_tokens() -> None:
    proposal = next(
        item
        for item in assess(company(), [fact("yc", "London, United Kingdom")])
        if item.field_name == "country"
    )
    assert proposal.status == "absent"
    assert proposal.proposed_value is None


def test_disagreeing_facts_conflict_deterministically() -> None:
    facts = [fact("yc", "10", stable_id="b"), fact("yc", "11", stable_id="a")]
    forward = assess(company(), facts)
    reverse = assess(company(), list(reversed(facts)))
    assert forward == reverse
    scale = next(item for item in forward if item.field_name == "company_scale")
    assert scale.status == "conflict"
    assert scale.proposed_value is None


def test_invalid_fact_blocks_competing_valid_fact() -> None:
    proposal = next(
        item
        for item in assess(
            company(), [fact("yc", "10"), fact("yc", "-2", stable_id="bad")]
        )
        if item.field_name == "company_scale"
    )
    assert proposal.status == "invalid"
    assert proposal.proposed_value is None


def test_existing_values_are_fill_missing_only_including_empty_tuple() -> None:
    populated = assess(
        company(business_sector=("Existing",), company_scale="0-10"),
        [fact("yc", '["New"]')],
    )
    assert (
        next(item for item in populated if item.field_name == "business_sector").status
        == "conflict"
    )
    assert (
        next(item for item in populated if item.field_name == "company_scale").status
        == "unchanged"
    )
    empty_tuple = assess(company(business_sector=()), [fact("yc", '["New"]')])
    sector = next(item for item in empty_tuple if item.field_name == "business_sector")
    assert sector.status == "proposed"
    assert sector.old_value == ()


def test_company_and_facts_are_immutable() -> None:
    record = company()
    with pytest.raises(FrozenInstanceError):
        record.country = "USA"  # type: ignore[misc]


@pytest.mark.parametrize(
    "location",
    ["Remote work, USA", "Remote-first, USA", "San Francisco (REMOTE), CA, USA"],
)
def test_remote_markers_anywhere_prevent_country_inference(location):
    proposal = next(
        p
        for p in assess(
            company(),
            [country_fact("yc", {"all_locations": location}, stable_id="remote")],
        )
        if p.field_name == "country"
    )
    assert proposal.status == "ambiguous"
    assert proposal.proposed_value is None


def test_country_state_name_ambiguity_abstains_without_a_city_lookup():
    proposal = next(
        p
        for p in assess(
            company(),
            [
                country_fact(
                    "yc",
                    {"all_locations": "Atlanta, Georgia"},
                    stable_id="ambiguous-state",
                )
            ],
        )
        if p.field_name == "country"
    )
    assert proposal.status == "ambiguous"
