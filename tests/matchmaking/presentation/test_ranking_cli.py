import io
import json
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

from huginn.matchmaking.presentation.ranking_cli import main


def payload():
    # A complete assessed-input example; no DB or model service is invoked.
    return {
        "schema_version": 1,
        "profile_reference": "example-provider",
        "profile_snapshot": {"offering": "Onboarding process review"},
        "assessment_method": "example-operator-v1",
        "as_of": "2026-10-25T12:00:00Z",
        "limit": 5,
        "seed": "example",
        "assessments": [
            {
                "company_id": "00000000-0000-4000-8000-000000000001",
                "assessment_id": "00000000-0000-4000-8000-000000000002",
                "service_fit": "direct",
                "business_context": "specific_context",
                "service_basis": "inferred",
                "context_basis": "observed",
                "industry_match": "match",
                "size_match": "unknown",
                "country_match": "unknown",
                "observations": [
                    {
                        "observation_id": "00000000-0000-4000-8000-000000000003",
                        "description": "We are building onboarding from scratch.",
                        "occurred_at": "2026-10-01T12:00:00Z",
                        "observed_at": "2026-10-24T12:00:00Z",
                        "source": "example",
                        "source_url": "https://example.invalid/source",
                    }
                ],
                "evidence": [
                    {
                        "observation_id": "00000000-0000-4000-8000-000000000003",
                        "quote": "building onboarding from scratch",
                    }
                ],
                "relevant_observation_ids": ["00000000-0000-4000-8000-000000000003"],
                "timing_observation_id": "00000000-0000-4000-8000-000000000003",
                "unknowns": ["Budget and consulting acceptance"],
                "rationale": "Specific onboarding research context.",
                "restrictions": [],
            }
        ],
    }


def invoke(text, *, output=False, existing=False):
    with tempfile.TemporaryDirectory() as directory:
        input_path = Path(directory) / "input.json"
        output_path = Path(directory) / "output.json"
        input_path.write_text(text)
        if existing:
            output_path.write_text("preserved")
        args = ["--input", str(input_path)]
        if output:
            args += ["--output", str(output_path)]
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = main(args)
        return (
            code,
            stdout.getvalue(),
            output_path.read_text() if output_path.exists() else None,
        )


def test_rank_operator_emits_complete_versioned_source_snapshot():
    code, text, _ = invoke(json.dumps(payload()))
    assert code == 0
    result = json.loads(text)
    assert result["algorithm_version"] == "research-ranking-v1"
    assert result["recommendations"][0]["score"] == 80
    assert result["recommendations"][0]["confidence"] == "medium"
    assert len(result["recommendations"][0]["recommendation_id"]) == 64
    assert (
        result["input_snapshot"]["assessments"][0]["observations"][0]["description"]
        == payload()["assessments"][0]["observations"][0]["description"]
    )
    assert result["score_is_probability"] is False


def test_rank_operator_rejects_duplicate_keys_nonfinite_and_unknown_fields():
    for text in (
        '{"schema_version":1,"schema_version":1}',
        '{"bad":NaN}',
        json.dumps({**payload(), "unexpected": True}),
    ):
        code, output, _ = invoke(text)
        assert code == 2
        assert "error" in json.loads(output)
        assert "recommendations" not in json.loads(output)


def test_rank_operator_preserves_existing_output_and_writes_exclusively():
    code, output, content = invoke(json.dumps(payload()), output=True, existing=True)
    assert code == 2
    assert content == "preserved"
    assert "error" in json.loads(output)
    code, output, content = invoke(json.dumps(payload()), output=True)
    assert code == 0
    assert json.loads(content)["recommendations"][0]["score"] == 80


def test_invalid_dates_and_future_sources_produce_no_partial_ranking():
    value = payload()
    value["assessments"][0]["observations"][0]["observed_at"] = "2027-01-01T00:00:00Z"
    code, output, _ = invoke(json.dumps(value))
    assert code == 2
    assert "error" in json.loads(output)


def test_empty_pool_is_honest_and_does_not_require_optional_dependency():
    value = payload()
    value["assessments"] = []
    code, output, _ = invoke(json.dumps(value))
    assert code == 0
    assert json.loads(output)["recommendations"] == []


def test_invalid_arguments_have_json_error_and_input_exit_code():
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        code = main(["--unrecognized"])
    assert code == 2
    assert "error" in json.loads(stdout.getvalue())
