from __future__ import annotations

from huginn.elt.silver.normalizers.yc_context import normalize_yc

BASE_HIT: dict[str, object] = {
    "id": 30405,
    "slug": "nao-labs",
    "name": "nao Labs",
    "one_liner": "Open Source Analytics Agent",
    "long_description": "Build and deploy analytics agents.",
    "tags": ["AI", "Developer Tools"],
    "tags_highlighted": ["AI"],
    "regions": ["North America"],
    "industries": ["B2B", "Developer Tools"],
    "industry": "Developer Tools",
    "subindustry": "Analytics",
    "team_size": 0,
    "all_locations": "San Francisco, CA",
    "batch": "Spring 2025",
    "status": "Active",
    "launched_at": 1744958361,
    "isHiring": False,
}


def test_normalize_yc_keeps_both_descriptions_and_source_taxonomy_separate():
    result = normalize_yc(BASE_HIT)

    assert result.source == "yc"
    assert result.stable_id == "30405"
    assert result.status == "captured"
    assert result.source_url == "https://www.ycombinator.com/companies/nao-labs"
    assert result.source_fields["one_liner"] == "Open Source Analytics Agent"
    assert (
        result.source_fields["long_description"] == "Build and deploy analytics agents."
    )
    assert result.source_fields["tags"] == ["AI", "Developer Tools"]
    assert result.source_fields["tags_highlighted"] == ["AI"]
    assert result.source_fields["regions"] == ["North America"]
    assert result.source_fields["industries"] == ["B2B", "Developer Tools"]
    assert result.source_fields["industry"] == "Developer Tools"
    assert result.source_fields["subindustry"] == "Analytics"
    assert result.source_fields["all_locations"] == "San Francisco, CA"
    assert result.source_fields["batch"] == "Spring 2025"
    assert result.source_fields["status"] == "Active"
    assert result.source_fields["isHiring"] is False
    assert result.source_fields["team_size"] == 0
    assert result.source_times == {"launched_at": 1744958361}
    assert result.normalized_text == (
        "Open Source Analytics Agent\n\nBuild and deploy analytics agents."
    )


def test_normalize_yc_keeps_unknown_hiring_and_absent_fields_unknown():
    hit = {key: value for key, value in BASE_HIT.items() if key != "isHiring"}

    result = normalize_yc(hit)

    assert result.status == "captured"
    assert "isHiring" not in result.source_fields
    assert "team_size" in result.source_fields
    assert result.source_fields["team_size"] == 0


def test_normalize_yc_captures_inactive_and_acquired_source_observations():
    for status in ("Inactive", "Acquired"):
        result = normalize_yc({**BASE_HIT, "status": status})
        assert result.status == "captured"
        assert result.source_fields["status"] == status
        assert result.source_fields["team_size"] == 0


def test_normalize_yc_does_not_invent_text_or_source_times():
    hit = {"id": 7, "slug": "quiet-co", "name": "Quiet Co"}

    result = normalize_yc(hit)

    assert result.status == "captured"
    assert result.normalized_text is None
    assert result.source_times == {}
    assert "isHiring" not in result.source_fields
    assert "launched_at" not in result.source_fields


def test_normalize_yc_reports_malformed_supplied_types_as_failed():
    for field, value in (
        ("isHiring", "false"),
        ("team_size", True),
        ("tags", "AI"),
        ("regions", ["North America", 3]),
        ("long_description", {"text": "description"}),
        ("launched_at", "1744958361"),
    ):
        result = normalize_yc({**BASE_HIT, field: value})
        assert result.status == "failed", field
        assert result.reason is not None, field


def test_normalize_yc_rejects_nonfinite_or_out_of_range_launch_times():
    for value in (float("inf"), float("nan"), 1e100):
        result = normalize_yc({**BASE_HIT, "launched_at": value})
        assert result.status == "failed"
        assert result.reason == (
            "launched_at must be a finite, representable timestamp or null"
        )
