from datetime import UTC, datetime, timedelta
from io import StringIO
from threading import Event, Thread
from time import monotonic, sleep
from uuid import uuid4

import psycopg
import pytest

from huginn.management.admin import main as admin_main
from huginn.management.application.commands.provisioning import ProvisionIdentity
from huginn.management.application.errors.errors import AuthenticationError
from huginn.management.application.services.account_admin import AccountAdminService
from huginn.management.application.services.authentication import (
    AuthenticationService,
)
from huginn.management.application.services.provisioning import (
    IdentityProvisioningService,
)
from huginn.management.config import ManagementConfig
from huginn.management.domain.errors.errors import ConflictError
from huginn.management.domain.value_objects.account import NewAccount
from huginn.management.domain.value_objects.professional_profile import (
    NewProfessionalProfile,
)
from huginn.management.domain.value_objects.session import NewSession
from huginn.management.domain.value_objects.user import NewUser
from huginn.management.persistence.database.client import (
    ManagementConnectionFactory,
    PsycopgDatabaseSession,
)
from huginn.management.persistence.database.unit_of_work import UnitOfWork
from huginn.management.persistence.errors.database import DatabaseError
from huginn.management.persistence.repositories.account import PostgresAccountRepository
from huginn.management.persistence.repositories.professional_profile import (
    PostgresProfessionalProfileRepository,
)
from huginn.management.persistence.repositories.session import PostgresSessionRepository
from huginn.management.persistence.repositories.user import PostgresUserRepository
from huginn.management.security.passwords import Password, verify_password
from huginn.management.security.tokens import digest_token, generate_token


def test_live_identity_repositories_mapping_defaults_and_case_conflict(
    management_database_url,
):
    with psycopg.connect(management_database_url) as connection:
        connection.execute("SAVEPOINT identity_repositories")
        accounts = PostgresAccountRepository(PsycopgDatabaseSession(connection))
        users = PostgresUserRepository(PsycopgDatabaseSession(connection))
        profiles = PostgresProfessionalProfileRepository(
            PsycopgDatabaseSession(connection)
        )
        username = f"Owner-{uuid4()}"
        account = accounts.create(NewAccount(username, "encoded-test-hash"))
        assert (
            accounts.get_by_normalized_username(f"  {username.lower()} ").id
            == account.id
        )
        user = users.create(
            NewUser(
                account.id,
                "Ada",
                "Lovelace",
                "ada@example.test",
                "+12025550123",
                "US",
                "UTC",
            )
        )
        profile = profiles.create(NewProfessionalProfile(user.id))
        assert (profile.headline, profile.professional_summary) == (None, None)
        assert (profile.skills, profile.experience, profile.previous_projects) == (
            (),
            (),
            (),
        )
        assert profiles.get_owned(user.id).id == profile.id
        with pytest.raises(ConflictError, match="username"):
            accounts.create(NewAccount(username.lower(), "another-encoded-hash"))
        connection.execute("ROLLBACK TO SAVEPOINT identity_repositories")
        connection.execute("RELEASE SAVEPOINT identity_repositories")


def test_live_login_row_lock_serializes_password_reset_and_session_revocation(
    management_database_url,
):
    username = f"Login-race-{uuid4()}"
    with psycopg.connect(management_database_url) as connection:
        account = PostgresAccountRepository(PsycopgDatabaseSession(connection)).create(
            NewAccount(username, "old-hash")
        )

    factory = ManagementConnectionFactory(management_database_url)
    entered_session_create, allow_login_commit = Event(), Event()
    reset_started, reset_finished = Event(), Event()
    errors = []

    class Throttle:
        def reserve(self, *_):
            return object()

        def record_failure(self, *_):
            pass

        def record_success(self, *_):
            pass

        def release(self, *_):
            pass

    class PausingSessions:
        def __init__(self, uow):
            self.repository = PostgresSessionRepository(uow.connection)

        def create(self, session):
            entered_session_create.set()
            if not allow_login_commit.wait(5):
                raise TimeoutError("login commit was not released")
            return self.repository.create(session)

    login = AuthenticationService(
        lambda: UnitOfWork(factory),
        ManagementConfig(management_database_url),
        Throttle(),
        accounts_factory=lambda uow: PostgresAccountRepository(uow.connection),
        sessions_factory=PausingSessions,
        verify_password_fn=lambda *_: True,
        needs_rehash_fn=lambda _: False,
        token_generator=iter(("login-token", "csrf-token")).__next__,
    )
    admin = AccountAdminService(
        lambda: UnitOfWork(factory),
        accounts_factory=lambda uow: PostgresAccountRepository(uow.connection),
        sessions_factory=lambda uow: PostgresSessionRepository(uow.connection),
    )

    def run_login():
        try:
            login.login(
                username=username,
                password="long enough password",
                client_ip="192.0.2.1",
            )
        except Exception as exc:  # surfaced in the owning test thread
            errors.append(exc)

    def run_reset():
        reset_started.set()
        try:
            admin.reset_password(username, "replacement password")
        except Exception as exc:  # surfaced in the owning test thread
            errors.append(exc)
        finally:
            reset_finished.set()

    login_thread = Thread(target=run_login)
    reset_thread = Thread(target=run_reset)
    try:
        login_thread.start()
        assert entered_session_create.wait(5)
        reset_thread.start()
        assert reset_started.wait(5)
        assert not reset_finished.wait(0.1)
        allow_login_commit.set()
        login_thread.join(5)
        reset_thread.join(5)
        assert not login_thread.is_alive() and not reset_thread.is_alive()
        assert errors == []
        with psycopg.connect(management_database_url) as connection:
            (revoked,) = connection.execute(
                "SELECT revoked_at FROM operational.sessions WHERE account_id = %s",
                (account.id,),
            ).fetchone()
        assert revoked is not None
    finally:
        allow_login_commit.set()
        login_thread.join(5)
        if reset_thread.is_alive():
            reset_thread.join(5)
        with psycopg.connect(management_database_url) as connection:
            connection.execute(
                "DELETE FROM operational.sessions WHERE account_id = %s", (account.id,)
            )
            connection.execute(
                "DELETE FROM operational.accounts WHERE id = %s", (account.id,)
            )


def test_live_password_change_rechecks_hash_after_owner_reset_lock(
    management_database_url,
):
    from werkzeug.security import generate_password_hash

    username = f"Password-change-race-{uuid4()}"
    old_password = "old password is long enough"
    reset_password = "reset password is long enough"
    with psycopg.connect(management_database_url) as connection:
        account = PostgresAccountRepository(PsycopgDatabaseSession(connection)).create(
            NewAccount(username, generate_password_hash(old_password))
        )

    factory = ManagementConnectionFactory(management_database_url)
    started, outcome = Event(), []
    service = AuthenticationService(
        lambda: UnitOfWork(factory),
        ManagementConfig(management_database_url),
        object(),
        accounts_factory=lambda uow: PostgresAccountRepository(uow.connection),
        sessions_factory=lambda uow: PostgresSessionRepository(uow.connection),
    )

    def change_with_stale_old_password():
        started.set()
        try:
            service.change_password(
                account.id,
                current_password=old_password,
                new_password="owner change password is long enough",
            )
        except Exception as exc:
            outcome.append(exc)

    worker = Thread(target=change_with_stale_old_password)
    try:
        with psycopg.connect(management_database_url) as reset_connection:
            repo = PostgresAccountRepository(PsycopgDatabaseSession(reset_connection))
            locked = repo.get_by_id_for_update(account.id)
            assert locked is not None
            assert (
                repo.set_password_hash(
                    account.id, generate_password_hash(reset_password)
                )
                is not None
            )

            worker.start()
            assert started.wait(5)
            deadline = monotonic() + 5
            waiting = False
            while monotonic() < deadline:
                with psycopg.connect(management_database_url) as observer:
                    waiting = observer.execute(
                        "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                        "WHERE wait_event_type = 'Lock' AND state = 'active' "
                        "AND query LIKE 'SELECT id, username, password_hash%FOR UPDATE%')"
                    ).fetchone()[0]
                if waiting:
                    break
                sleep(0.01)
            assert waiting, "password change did not wait on the reset row lock"

        worker.join(5)
        assert not worker.is_alive()
        assert len(outcome) == 1 and isinstance(outcome[0], AuthenticationError)
        with psycopg.connect(management_database_url) as connection:
            persisted = PostgresAccountRepository(
                PsycopgDatabaseSession(connection)
            ).get_by_id(account.id)
            assert persisted is not None
            assert verify_password(Password(reset_password), persisted.password_hash)
            assert not verify_password(
                Password("owner change password is long enough"),
                persisted.password_hash,
            )
    finally:
        worker.join(5)
        with psycopg.connect(management_database_url) as connection:
            connection.execute(
                "DELETE FROM operational.sessions WHERE account_id = %s", (account.id,)
            )
            connection.execute(
                "DELETE FROM operational.accounts WHERE id = %s", (account.id,)
            )


def test_live_provisioning_success_and_database_rollback_at_each_insert(
    management_database_url,
):
    stages = ("accounts", "users", "professional_profiles")
    triggers = [f"fail_identity_{table}_{uuid4().hex[:8]}" for table in stages]
    with psycopg.connect(management_database_url) as connection:
        connection.execute(
            "CREATE OR REPLACE FUNCTION operational.fail_identity_insert() "
            "RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
            "IF current_setting('huginn.fail_identity_stage', true) = TG_TABLE_NAME "
            "THEN RAISE EXCEPTION 'injected identity failure'; END IF; "
            "RETURN NEW; END $$"
        )
        for table, trigger in zip(stages, triggers, strict=True):
            connection.execute(
                f"CREATE TRIGGER {trigger} BEFORE INSERT ON operational.{table} "
                "FOR EACH ROW EXECUTE FUNCTION operational.fail_identity_insert()"
            )
        connection.commit()

    def service(stage=None):
        def connect(url, *, connect_timeout):
            connection = psycopg.connect(url, connect_timeout=connect_timeout)
            connection.execute(
                "SELECT set_config('huginn.fail_identity_stage', %s, false)",
                (stage or "",),
            )
            return connection

        factory = ManagementConnectionFactory(
            management_database_url, connector=connect
        )
        return IdentityProvisioningService(
            lambda: UnitOfWork(factory),
            accounts_factory=lambda uow: PostgresAccountRepository(uow.connection),
            users_factory=lambda uow: PostgresUserRepository(uow.connection),
            profiles_factory=lambda uow: PostgresProfessionalProfileRepository(
                uow.connection
            ),
            hash_password_fn=lambda _: "test-scrypt-hash",
        )

    def provision_values(username):
        return {
            "username": username,
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": f"{uuid4()}@example.test",
            "phone_number": "+12025550123",
            "country_of_residence": "US",
            "timezone": "UTC",
            "password": "a sufficiently long password",
        }

    def counts(username):
        with psycopg.connect(management_database_url) as connection:
            return connection.execute(
                "SELECT (SELECT count(*) FROM operational.accounts WHERE username = %s), "
                "(SELECT count(*) FROM operational.users u JOIN operational.accounts a "
                "ON a.id = u.account_id WHERE a.username = %s), "
                "(SELECT count(*) FROM operational.professional_profiles p JOIN "
                "operational.users u ON u.id = p.user_id JOIN operational.accounts a "
                "ON a.id = u.account_id WHERE a.username = %s)",
                (username, username, username),
            ).fetchone()

    try:
        successful = f"Owner-{uuid4()}"
        identity = service().provision(
            ProvisionIdentity(**provision_values(successful))
        )
        assert identity.username == successful
        assert counts(successful) == (1, 1, 1)
        with psycopg.connect(management_database_url) as connection:
            defaults = connection.execute(
                "SELECT headline, professional_summary, skills, experience, previous_projects "
                "FROM operational.professional_profiles WHERE user_id = %s",
                (identity.user_id,),
            ).fetchone()
        assert defaults == (None, None, [], [], [])

        for stage in stages:
            username = f"Failed-{stage}-{uuid4()}"
            with pytest.raises(DatabaseError, match="database operation failed"):
                service(stage).provision(
                    ProvisionIdentity(**provision_values(username))
                )
            assert counts(username) == (0, 0, 0)
    finally:
        with psycopg.connect(management_database_url) as connection:
            for table, trigger in zip(stages, triggers, strict=True):
                connection.execute(
                    f"DROP TRIGGER IF EXISTS {trigger} ON operational.{table}"
                )
            connection.execute(
                "DROP FUNCTION IF EXISTS operational.fail_identity_insert()"
            )
            connection.commit()


def test_live_admin_cli_lifecycle_safe_output_and_session_revocation(
    management_database_url, monkeypatch, capsys
):
    monkeypatch.setattr(
        "huginn.management.app.load_config",
        lambda: ManagementConfig(management_database_url),
    )
    username = f"Owner-{uuid4()}"
    monkeypatch.setattr(
        "sys.stdin", StringIO("initial password value\ninitial password value\n")
    )
    assert (
        admin_main(
            [
                "account",
                "provision",
                "--username",
                username,
                "--first-name",
                "Ada",
                "--last-name",
                "Lovelace",
                "--email",
                "ada@example.test",
                "--phone-number",
                "+12025550123",
                "--country-of-residence",
                "US",
                "--timezone",
                "UTC",
                "--password-stdin",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert username in output and "User " in output and "ProfessionalProfile " in output
    assert "initial password value" not in output and "scrypt" not in output

    with psycopg.connect(management_database_url) as connection:
        account_id, user_id, profile_id, previous_hash = connection.execute(
            "SELECT a.id, u.id, p.id, a.password_hash FROM operational.accounts a "
            "JOIN operational.users u ON u.account_id = a.id "
            "JOIN operational.professional_profiles p ON p.user_id = u.id "
            "WHERE a.username = %s",
            (username,),
        ).fetchone()
    assert all(
        str(identifier) in output for identifier in (account_id, user_id, profile_id)
    )
    assert admin_main(["account", "enable", "--username", username]) == 0
    capsys.readouterr()

    def create_session():
        with psycopg.connect(management_database_url) as connection:
            return connection.execute(
                "INSERT INTO operational.sessions (account_id, token_digest, csrf_digest, expires_at) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (
                    account_id,
                    uuid4().hex + uuid4().hex,
                    uuid4().hex + uuid4().hex,
                    datetime.now(UTC) + timedelta(hours=1),
                ),
            ).fetchone()[0]

    disable_session = create_session()
    assert admin_main(["account", "disable", "--username", username]) == 0
    assert "disabled" in capsys.readouterr().out
    with psycopg.connect(management_database_url) as connection:
        assert connection.execute(
            "SELECT revoked_at IS NOT NULL FROM operational.sessions WHERE id = %s",
            (disable_session,),
        ).fetchone()[0]
    assert admin_main(["account", "enable", "--username", username]) == 0
    capsys.readouterr()

    reset_session = create_session()
    monkeypatch.setattr(
        "sys.stdin",
        StringIO("replacement password value\nreplacement password value\n"),
    )
    assert (
        admin_main(
            ["account", "reset-password", "--username", username, "--password-stdin"]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "replacement password value" not in output and "scrypt" not in output
    with psycopg.connect(management_database_url) as connection:
        state = connection.execute(
            "SELECT a.status, a.password_hash, s.revoked_at IS NOT NULL, "
            "(SELECT id FROM operational.users WHERE account_id = a.id), "
            "(SELECT id FROM operational.professional_profiles WHERE user_id = %s) "
            "FROM operational.accounts a JOIN operational.sessions s ON s.account_id = a.id "
            "WHERE a.id = %s AND s.id = %s",
            (user_id, account_id, reset_session),
        ).fetchone()
    assert state[0] == "active" and state[1] != previous_hash and state[2]
    assert state[3:] == (user_id, profile_id)


def test_live_cli_disable_and_reset_roll_back_when_session_revocation_fails(
    management_database_url, monkeypatch, capsys
):
    factory = ManagementConnectionFactory(management_database_url)
    service = IdentityProvisioningService(
        lambda: UnitOfWork(factory),
        accounts_factory=lambda uow: PostgresAccountRepository(uow.connection),
        users_factory=lambda uow: PostgresUserRepository(uow.connection),
        profiles_factory=lambda uow: PostgresProfessionalProfileRepository(
            uow.connection
        ),
        hash_password_fn=lambda _: "old-hash",
    )
    username = f"Rollback-{uuid4()}"
    result = service.provision(
        ProvisionIdentity(
            username,
            "Grace",
            "Hopper",
            "grace@example.test",
            "+12025550123",
            "US",
            "UTC",
            "a sufficiently long password",
        )
    )
    session_id = uuid4()
    with psycopg.connect(management_database_url) as connection:
        connection.execute(
            "INSERT INTO operational.sessions (id, account_id, token_digest, csrf_digest, expires_at) "
            "VALUES (%s, %s, %s, %s, %s)",
            (
                session_id,
                result.account_id,
                uuid4().hex + uuid4().hex,
                uuid4().hex + uuid4().hex,
                datetime.now(UTC) + timedelta(hours=1),
            ),
        )
        connection.execute(
            "CREATE OR REPLACE FUNCTION operational.fail_session_revoke() RETURNS trigger "
            "LANGUAGE plpgsql AS $$ BEGIN IF NEW.revoked_at IS NOT NULL THEN "
            "RAISE EXCEPTION 'injected revocation failure'; END IF; RETURN NEW; END $$"
        )
        connection.execute(
            "CREATE TRIGGER fail_session_revoke BEFORE UPDATE ON operational.sessions "
            "FOR EACH ROW EXECUTE FUNCTION operational.fail_session_revoke()"
        )
        connection.commit()

    monkeypatch.setattr(
        "huginn.management.app.load_config",
        lambda: ManagementConfig(management_database_url),
    )
    try:
        assert admin_main(["account", "disable", "--username", username]) == 2
        monkeypatch.setattr(
            "sys.stdin", StringIO("replacement password\nreplacement password\n")
        )
        assert (
            admin_main(
                [
                    "account",
                    "reset-password",
                    "--username",
                    username,
                    "--password-stdin",
                ]
            )
            == 2
        )
        capsys.readouterr()
        with psycopg.connect(management_database_url) as connection:
            state = connection.execute(
                "SELECT a.status, a.password_hash, s.revoked_at, "
                "(SELECT count(*) FROM operational.users WHERE account_id = a.id), "
                "(SELECT count(*) FROM operational.professional_profiles p "
                "JOIN operational.users u ON u.id = p.user_id WHERE u.account_id = a.id) "
                "FROM operational.accounts a JOIN operational.sessions s ON s.account_id = a.id "
                "WHERE a.id = %s AND s.id = %s",
                (result.account_id, session_id),
            ).fetchone()
        assert state == ("active", "old-hash", None, 1, 1)
    finally:
        with psycopg.connect(management_database_url) as connection:
            connection.execute(
                "DROP TRIGGER IF EXISTS fail_session_revoke ON operational.sessions"
            )
            connection.execute(
                "DROP FUNCTION IF EXISTS operational.fail_session_revoke()"
            )
            connection.commit()


def test_live_sessions_persist_only_digests_and_enforce_active_state_transactionally(
    management_database_url,
):
    factory = ManagementConnectionFactory(management_database_url)
    provisioner = IdentityProvisioningService(
        lambda: UnitOfWork(factory),
        accounts_factory=lambda uow: PostgresAccountRepository(uow.connection),
        users_factory=lambda uow: PostgresUserRepository(uow.connection),
        profiles_factory=lambda uow: PostgresProfessionalProfileRepository(
            uow.connection
        ),
        hash_password_fn=lambda _: "session-test-hash",
    )
    username = f"Session-{uuid4()}"
    identity = provisioner.provision(
        ProvisionIdentity(
            username,
            "Ada",
            "Lovelace",
            f"{username}@example.test",
            "+12025550123",
            "US",
            "UTC",
            "a long owner password",
        )
    )

    with psycopg.connect(management_database_url) as connection:
        repository = PostgresSessionRepository(PsycopgDatabaseSession(connection))
        now = datetime.now(UTC)

        def create_session():
            session_token, csrf_token = generate_token(), generate_token()
            session = repository.create(
                NewSession(
                    identity.account_id,
                    digest_token(session_token),
                    digest_token(csrf_token),
                    now + timedelta(hours=1),
                )
            )
            return session, session_token, csrf_token

        connection.execute("SAVEPOINT session_rollback")
        rolled_back, rolled_back_token, _ = create_session()
        connection.execute("ROLLBACK TO SAVEPOINT session_rollback")
        assert repository.get_by_token_digest(digest_token(rolled_back_token)) is None

        current, current_token, current_csrf = create_session()
        sibling, sibling_token, _ = create_session()
        expiring, expiring_token, _ = create_session()
        connection.execute(
            "UPDATE operational.sessions SET expires_at = now() - interval '1 second' "
            "WHERE token_digest = %s",
            (digest_token(expiring_token),),
        )
        connection.commit()
        assert (
            repository.get_active_principal_by_token_digest(
                digest_token(expiring_token), datetime.now(UTC)
            )
            is None
        )

        stored = connection.execute(
            "SELECT token_digest, csrf_digest, created_at, expires_at FROM "
            "operational.sessions WHERE token_digest = %s",
            (digest_token(current_token),),
        ).fetchone()
        assert stored[0] == digest_token(current_token)
        assert stored[1] == digest_token(current_csrf)
        assert current_token not in stored[0]
        assert current_csrf not in stored[1]
        assert stored[2].tzinfo is not None and stored[3].tzinfo is not None
        principal = repository.get_active_principal_by_token_digest(
            digest_token(sibling_token), datetime.now(UTC)
        )
        assert (principal.account_id, principal.user_id) == (
            identity.account_id,
            identity.user_id,
        )
        repository.revoke_current(current.id, datetime.now(UTC))
        connection.commit()
        assert repository.get_by_token_digest(digest_token(current_token)).revoked_at
        assert (
            repository.get_by_token_digest(digest_token(sibling_token)).revoked_at
            is None
        )

        connection.execute(
            "UPDATE operational.accounts SET status = 'disabled' WHERE id = %s",
            (identity.account_id,),
        )
        connection.commit()
        assert (
            repository.get_active_principal_by_token_digest(
                digest_token(sibling_token), datetime.now(UTC)
            )
            is None
        )
        repository.revoke_for_account(identity.account_id, datetime.now(UTC))
        connection.commit()
        assert repository.get_by_token_digest(digest_token(sibling_token)).revoked_at
