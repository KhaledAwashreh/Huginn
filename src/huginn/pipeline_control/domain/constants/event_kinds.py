ALLOWED_EVENT_KINDS = frozenset(
    {
        "invocation_queued",
        "invocation_started",
        "stage_started",
        "stage_succeeded",
        "stage_failed",
        "stage_skipped",
        "source_started",
        "source_succeeded",
        "source_failed",
        "invocation_succeeded",
        "invocation_failed",
        "invocation_interrupted",
        "tracking_stale",
        "execution_recovered",
    }
)
