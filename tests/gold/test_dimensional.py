from huginn.gold.dimensional import apply_company_update


def test_no_history_row_when_only_type_1_fields_change():
    current = {"id": "c1", "name": "Acme", "icp_filter_pass": False}
    result = apply_company_update(current, {"name": "Acme Robotics"})

    assert result.history_snapshot is None


def test_history_row_written_when_a_type_2_field_changes():
    current = {
        "id": "c1",
        "business_sector": "fintech",
        "team_composition_signal": "unknown",
        "icp_filter_pass": False,
    }
    result = apply_company_update(current, {"icp_filter_pass": True})

    assert result.history_snapshot is not None
    assert result.history_snapshot["company_id"] == "c1"
    assert result.history_snapshot["icp_filter_pass"] is False
