import pytest
from pydantic import ValidationError

from huginn.management.schemas import (
    Experience,
    PreviousProject,
    ProfessionalCollections,
    Skill,
)


def test_omitted_collections_are_empty_arrays():
    assert ProfessionalCollections.model_validate({}).model_dump(mode="json") == {
        "skills": [],
        "experience": [],
        "previous_projects": [],
    }


@pytest.mark.parametrize("value", [None, ["Python"], [{"name": " "}], [{"name": 7}]])
def test_invalid_skills_are_rejected(value):
    with pytest.raises(ValidationError):
        ProfessionalCollections.model_validate({"skills": value})


def test_collections_round_trip_and_trim_required_names():
    payload = {
        "skills": [{"name": " Python "}],
        "experience": [
            {
                "organization": " Acme ",
                "role": " Consultant ",
                "summary": None,
                "start_month": "2024-01",
                "end_month": None,
                "is_current": True,
            }
        ],
        "previous_projects": [
            {
                "name": " Reporting API ",
                "description": " Delivered a reporting service. ",
            }
        ],
    }

    assert ProfessionalCollections.model_validate(payload).model_dump(mode="json") == {
        "skills": [{"name": "Python"}],
        "experience": [
            {
                "organization": "Acme",
                "role": "Consultant",
                "summary": None,
                "start_month": "2024-01",
                "end_month": None,
                "is_current": True,
            }
        ],
        "previous_projects": [
            {
                "name": "Reporting API",
                "description": "Delivered a reporting service.",
            }
        ],
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"unexpected": True},
        {"skills": [{"name": "Python", "proficiency": "expert"}]},
        {"skills": [{"name": "Python", "years": 5}]},
        {"experience": [{"organization": "Acme", "role": "Engineer", "extra": True}]},
        {
            "previous_projects": [
                {"name": "API", "description": "Built it", "extra": True}
            ]
        },
    ],
)
def test_unknown_fields_are_rejected_at_every_level(payload):
    with pytest.raises(ValidationError):
        ProfessionalCollections.model_validate(payload)


@pytest.mark.parametrize("field", ["skills", "experience", "previous_projects"])
def test_null_collections_are_rejected(field):
    with pytest.raises(ValidationError):
        ProfessionalCollections.model_validate({field: None})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("skills", "Python"),
        ("experience", "Acme"),
        ("previous_projects", "API"),
        ("skills", [[{"name": "Python"}]]),
        ("experience", [[{"organization": "Acme", "role": "Engineer"}]]),
        (
            "previous_projects",
            [[{"name": "API", "description": "Built it"}]],
        ),
    ],
)
def test_scalar_collections_and_nested_list_items_are_rejected(field, value):
    with pytest.raises(ValidationError):
        ProfessionalCollections.model_validate({field: value})


@pytest.mark.parametrize(
    "payload",
    [
        {"experience": [{"role": "Engineer"}]},
        {"experience": [{"organization": "Acme"}]},
        {"previous_projects": [{"description": "Built it"}]},
        {"previous_projects": [{"name": "API"}]},
    ],
)
def test_required_experience_and_project_fields_cannot_be_omitted(payload):
    with pytest.raises(ValidationError):
        ProfessionalCollections.model_validate(payload)


def test_optional_experience_fields_may_be_missing_or_null():
    collections = ProfessionalCollections.model_validate(
        {
            "experience": [
                {"organization": "Acme", "role": "Engineer"},
                {
                    "organization": "Acme",
                    "role": "Consultant",
                    "summary": None,
                    "start_month": None,
                    "end_month": None,
                },
            ]
        }
    )

    assert collections.model_dump(mode="json")["experience"] == [
        {
            "organization": "Acme",
            "role": "Engineer",
            "summary": None,
            "start_month": None,
            "end_month": None,
            "is_current": False,
        },
        {
            "organization": "Acme",
            "role": "Consultant",
            "summary": None,
            "start_month": None,
            "end_month": None,
            "is_current": False,
        },
    ]


@pytest.mark.parametrize("field", ["summary", "start_month", "end_month"])
def test_blank_optional_experience_strings_are_rejected(field):
    with pytest.raises(ValidationError):
        ProfessionalCollections.model_validate(
            {"experience": [{"organization": "Acme", "role": "Engineer", field: " "}]}
        )


def test_string_boolean_is_rejected():
    with pytest.raises(ValidationError):
        ProfessionalCollections.model_validate(
            {
                "experience": [
                    {
                        "organization": "Acme",
                        "role": "Engineer",
                        "is_current": "true",
                    }
                ]
            }
        )


@pytest.mark.parametrize("field", ["start_month", "end_month"])
@pytest.mark.parametrize(
    "value", ["2024-00", "2024-13", "24-01", "0000-01", "2024-1", "2024-01-01"]
)
def test_invalid_months_are_rejected(field, value):
    with pytest.raises(ValidationError):
        ProfessionalCollections.model_validate(
            {"experience": [{"organization": "Acme", "role": "Engineer", field: value}]}
        )


def test_boundary_and_equal_months_are_accepted():
    collections = ProfessionalCollections.model_validate(
        {
            "experience": [
                {
                    "organization": "Acme",
                    "role": "First",
                    "start_month": "0001-01",
                    "end_month": "0001-01",
                },
                {
                    "organization": "Acme",
                    "role": "Last",
                    "start_month": "9999-12",
                    "end_month": "9999-12",
                },
            ]
        }
    )

    dumped = collections.model_dump(mode="json")["experience"]
    assert (dumped[0]["start_month"], dumped[0]["end_month"]) == (
        "0001-01",
        "0001-01",
    )
    assert (dumped[1]["start_month"], dumped[1]["end_month"]) == (
        "9999-12",
        "9999-12",
    )


@pytest.mark.parametrize(
    "experience",
    [
        {
            "organization": "Acme",
            "role": "Engineer",
            "start_month": "2024-02",
            "end_month": "2024-01",
        },
        {
            "organization": "Acme",
            "role": "Engineer",
            "end_month": "2024-01",
            "is_current": True,
        },
    ],
)
def test_inconsistent_experience_months_are_rejected(experience):
    with pytest.raises(ValidationError):
        ProfessionalCollections.model_validate({"experience": [experience]})


def test_current_and_historical_work_allow_unknown_dates():
    collections = ProfessionalCollections.model_validate(
        {
            "experience": [
                {"organization": "Acme", "role": "Current", "is_current": True},
                {"organization": "Acme", "role": "Historical"},
            ]
        }
    )

    dumped = collections.model_dump(mode="json")["experience"]
    assert dumped[0]["is_current"] is True
    assert dumped[0]["start_month"] is None
    assert dumped[0]["end_month"] is None
    assert dumped[1]["is_current"] is False
    assert dumped[1]["start_month"] is None
    assert dumped[1]["end_month"] is None


def test_collection_order_and_duplicates_are_preserved():
    payload = {
        "skills": [{"name": "Python"}, {"name": "SQL"}, {"name": "Python"}],
        "experience": [
            {"organization": "Acme", "role": "First"},
            {"organization": "Acme", "role": "Second"},
        ],
        "previous_projects": [
            {"name": "API", "description": "Built it"},
            {"name": "API", "description": "Built it"},
        ],
    }

    dumped = ProfessionalCollections.model_validate(payload).model_dump(mode="json")
    assert [item["name"] for item in dumped["skills"]] == [
        "Python",
        "SQL",
        "Python",
    ]
    assert [item["role"] for item in dumped["experience"]] == ["First", "Second"]
    assert dumped["previous_projects"][0] == dumped["previous_projects"][1]


def test_default_collection_lists_are_independent():
    first = ProfessionalCollections.model_validate({})
    second = ProfessionalCollections.model_validate({})

    assert first.skills is not second.skills
    assert first.experience is not second.experience
    assert first.previous_projects is not second.previous_projects


@pytest.mark.parametrize(
    "model",
    [
        Skill.model_validate({"name": "Python"}),
        Experience.model_validate({"organization": "Acme", "role": "Engineer"}),
        PreviousProject.model_validate({"name": "API", "description": "Built it"}),
        ProfessionalCollections.model_validate({}),
    ],
)
def test_boundary_models_are_frozen_and_expose_pydantic_interfaces(model):
    assert isinstance(model.model_dump(mode="json"), dict)
    assert model.model_json_schema()["type"] == "object"
    with pytest.raises(ValidationError):
        model.unexpected = True


def test_json_schema_describes_extra_forbidden_arrays_of_objects():
    schema = ProfessionalCollections.model_json_schema()

    assert schema["additionalProperties"] is False
    for field, definition in (
        ("skills", "Skill"),
        ("experience", "Experience"),
        ("previous_projects", "PreviousProject"),
    ):
        assert schema["properties"][field]["type"] == "array"
        assert schema["properties"][field]["items"] == {"$ref": f"#/$defs/{definition}"}
        assert schema["$defs"][definition]["type"] == "object"
        assert schema["$defs"][definition]["additionalProperties"] is False
