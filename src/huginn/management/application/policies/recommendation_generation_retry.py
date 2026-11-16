from datetime import datetime, timedelta
from math import ceil


def generation_retry_after(
    successful_run_times: tuple[datetime, ...],
    now: datetime,
    *,
    limit: int = 6,
    window: timedelta = timedelta(minutes=15),
) -> int:
    """Return seconds until the oldest successful run leaves the rolling window."""
    recent = sorted(value for value in successful_run_times if value > now - window)
    if len(recent) < limit:
        return 0
    return max(1, ceil((recent[0] + window - now).total_seconds()))
