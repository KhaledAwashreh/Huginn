from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier, Event
from time import monotonic, sleep
from uuid import uuid4

import psycopg
import pytest

from huginn.management.application.errors.errors import AuthenticationError
from huginn.management.application.requests.current_session_request import (
    CurrentSessionRequest,
)
from huginn.management.application.services.current_session_service import (
    CurrentSessionService,
)
from huginn.management.domain.value_objects.common import Principal
from huginn.management.persistence.database.client import ManagementConnectionFactory
from huginn.management.persistence.database.unit_of_work import UnitOfWork
from huginn.management.persistence.repositories.session import PostgresSessionRepository
from huginn.management.security.tokens import digest_token


@pytest.fixture
def legacy_session(management_database_url):
    account, user, session = uuid4(), uuid4(), uuid4()
    token = f"credential-{uuid4()}"
    expiry = datetime.now(UTC) + timedelta(hours=1)
    with psycopg.connect(management_database_url) as conn:
        conn.execute(
            "INSERT INTO operational.accounts (id, username, password_hash) VALUES (%s,%s,%s)",
            (account, f"Bootstrap-{uuid4()}", "hash"),
        )
        conn.execute(
            "INSERT INTO operational.users (id, account_id, first_name, last_name, email, phone_number, country_of_residence) VALUES (%s,%s,'Ada','Lovelace',%s,'+12025550123','US')",
            (user, account, f"{uuid4()}@example.test"),
        )
        conn.execute(
            "INSERT INTO operational.sessions (id,account_id,token_digest,csrf_digest,expires_at) VALUES (%s,%s,%s,%s,%s)",
            (
                session,
                account,
                digest_token(token),
                digest_token("legacy-proof"),
                expiry,
            ),
        )
    try:
        yield CurrentSessionRequest(Principal(account, user), session, token)
    finally:
        with psycopg.connect(management_database_url) as conn:
            conn.execute(
                "DELETE FROM operational.sessions WHERE account_id=%s", (account,)
            )
            conn.execute(
                "DELETE FROM operational.users WHERE account_id=%s", (account,)
            )
            conn.execute("DELETE FROM operational.accounts WHERE id=%s", (account,))


def service(url, repository=None):
    factory = ManagementConnectionFactory(url)
    return CurrentSessionService(
        lambda: UnitOfWork(factory),
        sessions_factory=repository
        or (lambda work: PostgresSessionRepository(work.connection)),
    )


def test_live_concurrent_legacy_bootstraps_converge(
    management_database_url, legacy_session
):
    barrier = Barrier(2)

    class SynchronizedRepository(PostgresSessionRepository):
        def get_by_token_digest(self, digest):
            row = super().get_by_token_digest(digest)
            barrier.wait(timeout=5)
            return row

    reader = service(
        management_database_url, lambda work: SynchronizedRepository(work.connection)
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reader.execute, [legacy_session, legacy_session]))
    assert results[0] == results[1]
    with psycopg.connect(management_database_url) as conn:
        persisted = conn.execute(
            "SELECT csrf_digest, revoked_at FROM operational.sessions WHERE id=%s",
            (legacy_session.session_id,),
        ).fetchone()
    assert persisted == (digest_token(results[0].csrf_token), None)
    assert service(management_database_url).execute(legacy_session) == results[0]


@pytest.mark.parametrize("invalidation", ["revoke", "expire", "disable"])
def test_live_bootstrap_rechecks_after_concurrent_invalidation(
    management_database_url, legacy_session, invalidation
):
    read, proceed = Event(), Event()

    class PausingRepository(PostgresSessionRepository):
        def get_by_token_digest(self, digest):
            row = super().get_by_token_digest(digest)
            read.set()
            assert proceed.wait(5)
            return row

    reader = service(
        management_database_url, lambda work: PausingRepository(work.connection)
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(reader.execute, legacy_session)
        try:
            assert read.wait(5)
            with psycopg.connect(management_database_url) as conn:
                if invalidation == "disable":
                    conn.execute(
                        "UPDATE operational.accounts SET status='disabled' WHERE id=%s",
                        (legacy_session.principal.account_id,),
                    )
                elif invalidation == "revoke":
                    conn.execute(
                        "UPDATE operational.sessions SET revoked_at=clock_timestamp() WHERE id=%s",
                        (legacy_session.session_id,),
                    )
                else:
                    conn.execute(
                        "UPDATE operational.sessions SET expires_at=clock_timestamp() WHERE id=%s",
                        (legacy_session.session_id,),
                    )
        finally:
            proceed.set()
        with pytest.raises(AuthenticationError):
            future.result(timeout=5)
    with psycopg.connect(management_database_url) as conn:
        assert conn.execute(
            "SELECT csrf_digest FROM operational.sessions WHERE id=%s",
            (legacy_session.session_id,),
        ).fetchone()[0] == digest_token("legacy-proof")


def test_live_session_expiring_while_transition_waits_on_session_lock_is_rejected(
    management_database_url, legacy_session
):
    expiry = datetime.now(UTC) + timedelta(seconds=1)
    with psycopg.connect(management_database_url) as holder:
        holder.execute(
            "UPDATE operational.sessions SET expires_at=%s WHERE id=%s",
            (expiry, legacy_session.session_id),
        )
        holder.commit()
        holder.execute(
            "SELECT id FROM operational.sessions WHERE id=%s FOR UPDATE",
            (legacy_session.session_id,),
        )
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                service(management_database_url).execute, legacy_session
            )
            try:
                deadline = monotonic() + 5
                waiting = False
                while monotonic() < deadline:
                    with psycopg.connect(management_database_url) as observer:
                        waiting = observer.execute(
                            "SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE wait_event_type='Lock' AND state='active' AND query LIKE '%operational.sessions%')"
                        ).fetchone()[0]
                    if waiting:
                        break
                    sleep(0.01)
                assert waiting, "bootstrap did not wait on the session row lock"
                while datetime.now(UTC) <= expiry:
                    sleep(0.01)
            finally:
                holder.commit()
            with pytest.raises(AuthenticationError):
                future.result(timeout=5)
