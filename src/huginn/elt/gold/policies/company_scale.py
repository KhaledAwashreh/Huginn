"""Pure company-scale bucketing policy; see architecture document section 4.3."""

from __future__ import annotations

_SCALE_BANDS: tuple[tuple[int, str], ...] = (
    (10, "0-10"),
    (100, "11-100"),
    (1000, "101-1000"),
)
_SCALE_TOP_BAND = "1001+"


def team_size_to_scale(team_size: int | None) -> str | None:
    """Map a valid nonnegative integer headcount to Huginn's Gold bands."""
    if (
        team_size is None
        or isinstance(team_size, bool)
        or not isinstance(team_size, int)
        or team_size < 0
    ):
        return None
    for upper, band in _SCALE_BANDS:
        if team_size <= upper:
            return band
    return _SCALE_TOP_BAND
