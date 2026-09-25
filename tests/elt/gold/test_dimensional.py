from huginn.elt.gold.dimensional import apply_company_update


def test_no_history_row_when_only_type_1_fields_change():
    current = {"id": "c1", "name": "Acme", "icp_filter_pass": False}
    result = apply_company_update(current, {"name": "Acme Robotics"})

    assert result.history_snapshot is None


def test_history_row_written_when_a_type_2_field_changes():
    current = {
        "id": "c1",
        "business_sector": ["fintech"],
        "team_composition_signal": "unknown",
        "icp_filter_pass": False,
    }
    result = apply_company_update(current, {"icp_filter_pass": True})

    assert result.history_snapshot is not None
    assert result.history_snapshot["company_id"] == "c1"
    assert result.history_snapshot["icp_filter_pass"] is False


def test_no_history_row_when_business_sector_repeats_the_same_list():
    """The equality has to survive the column becoming an array.

    Comparing a fresh list against a stored one is True in Python, but only
    because both sides are lists of the same strings in the same order. A
    comparison that stringified either side, or that treated a list as
    always-changed, would pass this file's other tests and quietly write a
    CompanyHistory row on every single Gold run.
    """
    current = {"id": "c1", "business_sector": ["b2b", "fintech"]}

    result = apply_company_update(current, {"business_sector": ["b2b", "fintech"]})

    assert result.history_snapshot is None


def test_history_row_written_when_business_sector_gains_an_industry():
    """A company moving from one sector to two is a real change, not noise."""
    current = {"id": "c1", "business_sector": ["fintech"]}

    result = apply_company_update(current, {"business_sector": ["fintech", "b2b"]})

    assert result.history_snapshot is not None
    assert result.history_snapshot["business_sector"] == ["fintech"]


def test_history_row_written_when_business_sector_becomes_known_for_the_first_time():
    """NULL to a list is the change that matters most: unclassified to classified."""
    current = {"id": "c1", "business_sector": None}

    result = apply_company_update(current, {"business_sector": ["healthcare"]})

    assert result.history_snapshot is not None
