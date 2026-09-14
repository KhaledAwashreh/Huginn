from huginn.elt.bronze.watermark import compute_content_hash, normalize_field


def test_normalize_field_collapses_whitespace_and_lowercases():
    assert normalize_field("  Acme   Robotics \n") == "acme robotics"


def test_compute_content_hash_is_stable_for_identical_stable_fields():
    payload_a = {"title": "Backend Engineer", "noise": "counter=1"}
    payload_b = {"title": "Backend Engineer", "noise": "counter=2"}
    stable_fields = ["title"]

    assert compute_content_hash(payload_a, stable_fields) == compute_content_hash(
        payload_b, stable_fields
    )


def test_compute_content_hash_changes_when_a_stable_field_changes():
    stable_fields = ["title"]
    hash_a = compute_content_hash({"title": "Backend Engineer"}, stable_fields)
    hash_b = compute_content_hash({"title": "Frontend Engineer"}, stable_fields)

    assert hash_a != hash_b


def test_compute_content_hash_ignores_whitespace_and_case_only_differences():
    stable_fields = ["title"]
    hash_a = compute_content_hash({"title": "Backend Engineer"}, stable_fields)
    hash_b = compute_content_hash({"title": "  backend   engineer"}, stable_fields)

    assert hash_a == hash_b


def test_compute_content_hash_distinguishes_a_missing_field_from_an_empty_string():
    """Regression, KAN-47: a field absent from the payload and a field
    present but explicitly an empty string must not hash identically, or a
    field appearing/disappearing between fetches is silently masked as "no
    change" (architecture-notes/opencorporates-fetch-plan.md section 6).
    """
    stable_fields = ["some_field"]
    hash_missing = compute_content_hash({}, stable_fields)
    hash_present_empty = compute_content_hash({"some_field": ""}, stable_fields)

    assert hash_missing != hash_present_empty
