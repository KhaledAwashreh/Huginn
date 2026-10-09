"""Allowlisted operational messages; pipeline control design section 4."""

from huginn.pipeline_control.application.errors.execution import (
    ExecutorTerminationUnprovenError,
    TrackingUncertainError,
)


def map_safe_event(error: BaseException) -> tuple[str, str]:
    if isinstance(error, TrackingUncertainError):
        return (
            "tracking_unavailable",
            "Execution interrupted because tracking became unavailable.",
        )
    if isinstance(error, ExecutorTerminationUnprovenError):
        return (
            "executor_stop_unproven",
            "Execution remains blocked pending operator recovery.",
        )
    return "execution_failed", "Pipeline execution failed."
