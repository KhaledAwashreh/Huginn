"""Safe driver-independent failures with structured database metadata."""


class DatabaseError(Exception):
    def __init__(
        self,
        *,
        sqlstate: str | None = None,
        constraint_name: str | None = None,
        error_name: str = "DatabaseError",
    ) -> None:
        super().__init__("database operation failed")
        self.sqlstate = sqlstate
        self.constraint_name = constraint_name
        self.error_name = error_name


class IntegrityError(DatabaseError):
    """A database integrity failure; repositories translate known constraints."""
