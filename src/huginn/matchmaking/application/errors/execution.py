class MatchmakingExecutionError(Exception):
    """Base class for safe application execution failures."""

    reason = "database_failure"


class DatabaseUnavailableExecutionError(MatchmakingExecutionError):
    reason = "database_unavailable"


class DatabaseFailureExecutionError(MatchmakingExecutionError):
    reason = "database_failure"


class RetriesExhaustedExecutionError(MatchmakingExecutionError):
    reason = "retries_exhausted"


class CommitOutcomeUnknownExecutionError(MatchmakingExecutionError):
    reason = "commit_outcome_unknown"


class InputValidationError(ValueError):
    code = "invalid_input"


class ConfigurationError(ValueError):
    code = "invalid_configuration"
