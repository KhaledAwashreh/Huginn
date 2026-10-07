class RetryableTransactionError(Exception):
    pass


class DatabaseOperationError(Exception):
    pass


class DataIntegrityError(DatabaseOperationError):
    pass


class DatabaseUnavailableError(Exception):
    pass


class CommitOutcomeUnknownError(Exception):
    pass
