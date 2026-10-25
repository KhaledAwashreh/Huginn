from huginn.elt.gold.policies.company_scale import team_size_to_scale


def test_missing_or_invalid_headcount_has_no_scale() -> None:
    assert team_size_to_scale(None) is None
    assert team_size_to_scale(-1) is None
    assert team_size_to_scale(True) is None
    assert team_size_to_scale(1.5) is None  # type: ignore[arg-type]


def test_zero_is_a_valid_small_company_headcount() -> None:
    assert team_size_to_scale(0) == "0-10"


def test_headcount_bands_keep_existing_boundaries() -> None:
    assert [team_size_to_scale(size) for size in (1, 10, 11, 100, 101, 1000, 1001)] == [
        "0-10",
        "0-10",
        "11-100",
        "11-100",
        "101-1000",
        "101-1000",
        "1001+",
    ]


def test_real_observed_headcount_extremes_keep_their_bands() -> None:
    assert team_size_to_scale(2) == "0-10"
    assert team_size_to_scale(227) == "101-1000"
    assert team_size_to_scale(7000) == "1001+"
    assert team_size_to_scale(10000) == "1001+"
