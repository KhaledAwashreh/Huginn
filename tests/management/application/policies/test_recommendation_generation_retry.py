from datetime import UTC, datetime, timedelta

from huginn.management.application.policies.recommendation_generation_retry import (
    generation_retry_after,
)

NOW = datetime(2026, 11, 14, 12, tzinfo=UTC)


def test_under_limit_has_no_retry_even_for_empty_successful_history():
    assert generation_retry_after((NOW - timedelta(minutes=14),) * 5, NOW) == 0


def test_sixth_successful_run_waits_until_oldest_run_leaves_window():
    runs = tuple(NOW - timedelta(minutes=value) for value in (14, 12, 10, 8, 6, 1))
    assert generation_retry_after(runs, NOW) == 60


def test_runs_at_exact_window_boundary_do_not_count():
    runs = (NOW - timedelta(minutes=15),) * 6
    assert generation_retry_after(runs, NOW) == 0
