"""Explicit management transaction lifecycle, independent of its driver."""

from contextlib import suppress
from types import TracebackType
from typing import Self

from huginn.management.persistence.contracts.database import (
    ConnectionFactory,
    DatabaseSession,
)


class UnitOfWork:
    """One explicit transaction and connection for an application operation."""

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._connection_factory = connection_factory
        self.connection: DatabaseSession | None = None
        self._finished = False

    def __enter__(self) -> Self:
        self.connection = self._connection_factory.connect()
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
        except BaseException:
            self._finished = True
            with suppress(BaseException):
                connection.close()
            self.connection = None
            raise
        try:
            connection.close()
        finally:
            self.connection = None
        return False

    def commit(self) -> None:
        connection = self._require_connection()
        if self._finished:
            raise RuntimeError("unit of work is already finished")
        try:
            connection.commit()
        except BaseException:
            self._finished = True
            with suppress(BaseException):
                connection.rollback()
            raise
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
