import json
from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from huginn.management.requests.ideal_client_profile import (
    CompanySize,
    Exclusion,
    Geography,
    Industry,
)


@pytest.mark.parametrize("band", ["0-10", "11-100", "101-1000", "1001+"])
def test_company_size_accepts_gold_bands(band):
    assert CompanySize.model_validate({"band": band}).band == band


@pytest.mark.parametrize(
    "payload, expected",
    [
        ({"kind": "country", "value": " Germany "}, ("country", "Germany")),
        ({"kind": "region", "value": " Europe "}, ("region", "Europe")),
    ],
)
def test_geography_accepts_and_trims_each_variant(payload, expected):
    value = TypeAdapter(Geography).validate_python(payload)
    assert (value.kind, value.value) == expected


@pytest.mark.parametrize(
    "payload, expected",
    [
        (
            {"kind": "company", "company_id": str(uuid4())},
            "company",
        ),
        ({"kind": "industry", "name": "  SaaS "}, "industry"),
        (
            {
                "kind": "geography",
                "geography": {"kind": "country", "value": " Germany "},
            },
            "geography",
        ),
    ],
)
def test_exclusion_accepts_each_tagged_variant(payload, expected):
    value = TypeAdapter(Exclusion).validate_json(json.dumps(payload))
    assert value.kind == expected
    if expected == "company":
        assert value.company_id is not None
    if expected == "industry":
        assert value.name == "SaaS"
    if expected == "geography":
        assert value.geography.value == "Germany"


def test_company_exclusion_parses_uuid_from_json_string_but_not_invalid_value():
    identifier = uuid4()
    adapter = TypeAdapter(Exclusion)
    parsed = adapter.validate_json(
        '{"kind":"company","company_id":"' + str(identifier) + '"}'
    )
    assert parsed.company_id == identifier
    with pytest.raises(ValidationError):
        adapter.validate_json('{"kind":"company","company_id":"bad"}')
    assert (
        adapter.validate_python(
            {"kind": "company", "company_id": str(identifier)}
        ).company_id
        == identifier
    )
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "company", "company_id": 12})


@pytest.mark.parametrize(
    "model,payload",
    [
        (Geography, {"value": "Germany"}),
        (Geography, {"kind": "continent", "value": "Europe"}),
        (Geography, {"kind": "country", "value": "Germany", "extra": 1}),
        (Geography, {"kind": "country", "value": 1}),
        (CompanySize, {"kind": "company_size", "band": "0-10"}),
        (CompanySize, {"band": "10-100"}),
        (CompanySize, {"band": 11}),
        (Industry, {"name": " "}),
        (Industry, {"name": "SaaS", "extra": True}),
        (Industry, {"name": 10}),
        (Exclusion, {"company_id": str(uuid4())}),
        (Exclusion, {"kind": "person", "company_id": str(uuid4())}),
        (Exclusion, {"kind": "company", "company_id": str(uuid4()), "extra": 1}),
        (Exclusion, {"kind": "industry", "name": " ", "company_id": str(uuid4())}),
        (Exclusion, {"kind": "geography", "geography": {"kind": "city", "value": "x"}}),
        (
            Exclusion,
            {"kind": "geography", "geography": {"kind": "region", "value": " "}},
        ),
    ],
)
def test_criterion_models_reject_missing_or_invalid_tags_extras_and_coercion(
    model, payload
):
    with pytest.raises(ValidationError):
        TypeAdapter(model).validate_python(payload)


def test_industry_collection_preserves_order_and_duplicates():
    values = TypeAdapter(list[Industry]).validate_python(
        [{"name": " SaaS "}, {"name": "Fintech"}, {"name": "SaaS"}]
    )
    assert [item.name for item in values] == ["SaaS", "Fintech", "SaaS"]


def test_exclusion_collection_preserves_order_and_duplicates():
    identifier = uuid4()
    values = TypeAdapter(list[Exclusion]).validate_python(
        [
            {"kind": "industry", "name": " SaaS "},
            {"kind": "company", "company_id": identifier},
            {"kind": "industry", "name": "SaaS"},
        ]
    )
    assert [item.kind for item in values] == ["industry", "company", "industry"]
    assert [item.name for item in values if item.kind == "industry"] == [
        "SaaS",
        "SaaS",
    ]
