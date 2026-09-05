"""Company/CompanyHistory update logic. See ADR-0002 and architecture
document section 4.3.

`Company` holds exactly one row per company, always, overwritten in
place. `CompanyHistory` gets a new row only when a Type 2 tracked field
changes. The exact column-by-column classification beyond these three
fields is pending the concrete schema (Jira KAN-20).
"""

from __future__ import annotations

from dataclasses import dataclass

TYPE_2_TRACKED_FIELDS = ("business_sector", "team_composition_signal", "icp_filter_pass")
"""Fields that trigger a CompanyHistory row on change. See ADR-0002.
Everything else on Company is Type 1: overwritten in place, no history.
"""


@dataclass(frozen=True)
class CompanyUpdate:
    """Result of comparing a company's current row against new values.

    `history_snapshot` is None when no Type 2 field changed, meaning
    the caller should just overwrite `Company` in place with no new
    `CompanyHistory` row.
    """

    new_values: dict
    history_snapshot: dict | None


def apply_company_update(current: dict, new_values: dict) -> CompanyUpdate:
    """Decide whether an update to a Company row requires a CompanyHistory
    row. See ADR-0002: history is written only when a Type 2 tracked field
    changes; Type 1 fields always just overwrite in place.
    """
    changed_type_2 = any(
        field in new_values and new_values[field] != current.get(field)
        for field in TYPE_2_TRACKED_FIELDS
    )
    if not changed_type_2:
        return CompanyUpdate(new_values=new_values, history_snapshot=None)

    snapshot = {field: current.get(field) for field in TYPE_2_TRACKED_FIELDS}
    snapshot["company_id"] = current.get("id")
    return CompanyUpdate(new_values=new_values, history_snapshot=snapshot)
