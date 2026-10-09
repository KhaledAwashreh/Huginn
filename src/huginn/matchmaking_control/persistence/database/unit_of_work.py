from contextlib import suppress
from types import TracebackType
from typing import Self

from huginn.management.persistence.contracts.database import (
    ConnectionFactory,
    DatabaseSession,
)
from huginn.matchmaking_control.persistence.queries.target_user_query import (
    PostgresTargetUserQuery,
)
from huginn.matchmaking_control.persistence.repositories.run_repository import (
    PostgresRunRepository,
)


class PostgresMatchmakingControlUnitOfWork:
    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._connection_factory = connection_factory
        self.connection: DatabaseSession | None = None
        self.runs: PostgresRunRepository
        self.target_users: PostgresTargetUserQuery
        self._finished = False

    def __enter__(self) -> Self:
        self.connection = self._connection_factory.connect()
        self.runs = PostgresRunRepository(self.connection)
        self.target_users = PostgresTargetUserQuery(self.connection)
        self._finished = False
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        connection = self._require_connection()
        if exc_value is not None:
            if not self._finished:
                self._finished = True
                with suppress(BaseException):
                    connection.rollback()
            with suppress(BaseException):
                connection.close()
            self.connection = None
            return False
        try:
            if not self._finished:
                self.rollback()
        finally:
            connection.close()
            self.connection = None
        return False

    def commit(self) -> None:
        connection = self._require_connection()
        if self._finished:
            raise RuntimeError("unit of work is already finished")
        connection.commit()
        self._finished = True

    def rollback(self) -> None:
        connection = self._require_connection()
        if self._finished:
            raise RuntimeError("unit of work is already finished")
        connection.rollback()
        self._finished = True

    def _require_connection(self) -> DatabaseSession:
        if self.connection is None:
            raise RuntimeError("unit of work is not active")
        return self.connection
