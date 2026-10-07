"""Repeatable Read transactions and read-only readiness, design sections 8/9."""

import logging
from types import TracebackType
from typing import Self

import psycopg
from psycopg import IsolationLevel

from huginn.matchmaking.persistence.errors.database import (
    CommitOutcomeUnknownError,
    DatabaseOperationError,
    DatabaseUnavailableError,
    RetryableTransactionError,
)
from huginn.matchmaking.persistence.repositories.sql.candidates import (
    SqlCandidateRepository,
)
from huginn.matchmaking.persistence.repositories.sql.configuration import (
    SqlConfigurationRepository,
)
from huginn.matchmaking.persistence.repositories.sql.matches import SqlMatchRepository

logger = logging.getLogger(__name__)


def _translate(
    error: psycopg.Error, *, committing: bool = False
) -> DatabaseOperationError | RetryableTransactionError | CommitOutcomeUnknownError:
    if error.sqlstate in ("40001", "40P01"):
        return RetryableTransactionError("Transaction rejected")
    if committing and (
        error.sqlstate is None
        or error.sqlstate.startswith("08")
        or error.sqlstate in ("57P01", "57P02", "57P03")
    ):
        return CommitOutcomeUnknownError("Commit acknowledgement unavailable")
    return DatabaseOperationError("Database operation failed")


class SqlMatchmakingUnitOfWork:
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._connection: psycopg.Connection | None = None
        self._committed = False
        self._uncertain = False

    def __enter__(self) -> Self:
        try:
            self._connection = psycopg.connect(self._database_url, connect_timeout=5)
        except psycopg.Error as exc:
            raise DatabaseUnavailableError("Database connection unavailable") from exc
        try:
            self._connection.isolation_level = IsolationLevel.REPEATABLE_READ
            self.configuration = SqlConfigurationRepository(self._connection)
            self.candidates = SqlCandidateRepository(self._connection)
            self.matches = SqlMatchRepository(self._connection)
        except psycopg.Error as exc:
            self._cleanup()
            raise _translate(exc) from exc
        except BaseException:
            self._cleanup()
            raise
        return self

    def commit(self) -> None:
        assert self._connection is not None
        try:
            self._connection.commit()
        except psycopg.Error as exc:
            translated = _translate(exc, committing=True)
            self._uncertain = isinstance(translated, CommitOutcomeUnknownError)
            raise translated from exc
        self._committed = True

    def rollback(self) -> None:
        if self._connection is not None and not self._uncertain:
            try:
                self._connection.rollback()
            except psycopg.Error as exc:
                raise _translate(exc) from exc

    def _cleanup(self) -> None:
        if self._connection is None:
            return
        if not self._committed and not self._uncertain:
            try:
                self._connection.rollback()
            except Exception:
                logger.warning("Matchmaking rollback cleanup failed")
        try:
            self._connection.close()
        except Exception:
            logger.warning("Matchmaking connection cleanup failed")

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        self._cleanup()
        if isinstance(exc_value, psycopg.Error):
            raise _translate(exc_value) from exc_value
        return False


def check_readiness(database_url: str) -> None:
    try:
        connection = psycopg.connect(database_url, connect_timeout=5)
    except psycopg.Error as exc:
        raise DatabaseUnavailableError("Database connection unavailable") from exc
    try:
        connection.read_only = True
        for query in (
            "SELECT u.id, u.account_id, a.id, a.status FROM operational.users u LEFT JOIN operational.accounts a ON a.id=u.account_id LIMIT 0",
            "SELECT s.id,s.user_id,s.name,s.service_offering_id,s.ideal_client_profile_id,s.is_active,o.id,o.user_id,p.id,p.user_id,p.industries,p.company_sizes,p.geographies,p.exclusions FROM operational.client_discovery_strategies s LEFT JOIN operational.service_offerings o ON FALSE LEFT JOIN operational.ideal_client_profiles p ON FALSE LIMIT 0",
            "SELECT id,business_sector,company_scale,country FROM gold.company LIMIT 0",
            "SELECT company_id,occurred_at FROM gold.company_signal LIMIT 0",
            "SELECT id,user_id,company_id,status,notes,created_at,updated_at FROM operational.match LIMIT 0",
        ):
            connection.execute(query)
        row = connection.execute("""
            SELECT EXISTS (
                SELECT 1 FROM pg_constraint c
                JOIN pg_index i ON i.indexrelid=c.conindid
                JOIN pg_class idx ON idx.oid=c.conindid
                JOIN pg_am am ON am.oid=idx.relam
                WHERE c.conrelid='operational.match'::regclass
                AND c.connamespace='operational'::regnamespace
                AND c.conname='match_user_company_unique'
                AND idx.relnamespace='operational'::regnamespace
                AND idx.relname='match_user_company_unique' AND idx.relkind='i'
                AND c.contype='u' AND NOT c.condeferrable AND NOT c.condeferred
                AND c.convalidated AND i.indrelid=c.conrelid
                AND c.conkey=ARRAY[
                    (SELECT attnum FROM pg_attribute WHERE attrelid=c.conrelid AND attname='user_id' AND NOT attisdropped),
                    (SELECT attnum FROM pg_attribute WHERE attrelid=c.conrelid AND attname='company_id' AND NOT attisdropped)
                ]::smallint[]
                AND ARRAY(SELECT unnest(i.indkey::smallint[]))=c.conkey
                AND i.indisunique AND i.indisvalid AND i.indisready
                AND i.indislive AND i.indimmediate AND i.indnkeyatts=2 AND i.indnatts=2
                AND i.indexprs IS NULL AND i.indpred IS NULL AND am.amname='btree'
            )
        """).fetchone()
        if row is None or not row[0]:
            raise DatabaseOperationError(
                "Required Match identity constraint unavailable"
            )
    except psycopg.Error as exc:
        raise DatabaseOperationError("Database readiness operation failed") from exc
    finally:
        try:
            connection.close()
        except Exception:
            logger.warning("Matchmaking readiness cleanup failed")
