from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from huginn.management.schemas import ProfessionalCollections

MANAGEMENT_TABLES = {"accounts", "users", "professional_profiles"}
EXISTING_OPERATIONAL_TABLES = {
    "employee",
    "match",
    "match_score",
    "match_feedback",
    "activity",
    "communication",
    "communication_version",
    "communication_revision",
    "communication_turn",
}
USER_TEXT_FIELDS = (
    "first_name",
    "last_name",
    "email",
    "phone_number",
    "country_of_residence",
)
COLLECTION_FIELDS = ("skills", "experience", "previous_projects")
INVALID_TRIMMED_TEXT = (None, "", " ", "\t", "\n", " leading", "trailing ")


@contextmanager
def _connection(database_url: str) -> Iterator[psycopg.Connection]:
    with psycopg.connect(database_url) as conn:
        try:
            yield conn
        finally:
            conn.rollback()


def _insert_account(
    conn: psycopg.Connection,
    *,
    username: str | None = None,
) -> UUID:
    return conn.execute(
        "INSERT INTO operational.accounts (username, password_hash) "
        "VALUES (%s, %s) RETURNING id",
        (username or f"account-{uuid4()}", "test-hash-not-a-real-credential"),
    ).fetchone()[0]


def _insert_user(conn: psycopg.Connection, account_id: UUID) -> UUID:
    return conn.execute(
        """
        INSERT INTO operational.users (
            account_id, first_name, last_name, email, phone_number,
            country_of_residence, timezone
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            account_id,
            "Ada",
            "Lovelace",
            f"ada-{uuid4()}@example.test",
            "+970599000000",
            "Palestine",
            "Asia/Hebron",
        ),
    ).fetchone()[0]


def _insert_profile(conn: psycopg.Connection, user_id: UUID) -> UUID:
    return conn.execute(
        "INSERT INTO operational.professional_profiles (user_id) "
        "VALUES (%s) RETURNING id",
        (user_id,),
    ).fetchone()[0]


def _assert_uuid_and_aware_timestamps(row) -> None:
    assert isinstance(row[0], UUID)
    assert row[1].utcoffset() is not None
    assert row[2].utcoffset() is not None


def test_fresh_bootstrap_has_management_and_existing_tables(
    management_database_url,
):
    with psycopg.connect(management_database_url) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'operational'"
            )
        }
        user_columns = {
            row[0]
            for row in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'operational' AND table_name = 'users'"
            )
        }

    assert tables >= MANAGEMENT_TABLES
    assert tables >= EXISTING_OPERATIONAL_TABLES
    assert "icp_profile" not in user_columns


def test_empty_management_database_has_no_application_schemas(
    empty_management_database_url,
):
    with psycopg.connect(empty_management_database_url) as conn:
        schemas = {
            row[0]
            for row in conn.execute(
                "SELECT schema_name FROM information_schema.schemata"
            )
        }

    assert {"ops", "bronze", "silver", "gold", "operational"}.isdisjoint(schemas)


def test_account_bootstrap_has_uuid_and_aware_timestamps(management_database_url):
    with _connection(management_database_url) as conn:
        row = conn.execute(
            "INSERT INTO operational.accounts (username, password_hash) "
            "VALUES (%s, %s) RETURNING id, status, created_at, updated_at",
            ("schema-test", "test-hash-not-a-real-credential"),
        ).fetchone()

        assert isinstance(row[0], UUID)
        assert row[1] == "active"
        assert row[2].utcoffset() is not None
        assert row[3].utcoffset() is not None


def test_user_and_profile_bootstrap_have_uuid_and_aware_timestamps(
    management_database_url,
):
    with _connection(management_database_url) as conn:
        account_id = _insert_account(conn)
        user_row = conn.execute(
            """
            INSERT INTO operational.users (
                account_id, first_name, last_name, email, phone_number,
                country_of_residence
            ) VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, created_at, updated_at
            """,
            (
                account_id,
                "Ada",
                "Lovelace",
                f"ada-{uuid4()}@example.test",
                "+970599000000",
                "Palestine",
            ),
        ).fetchone()
        profile_row = conn.execute(
            "INSERT INTO operational.professional_profiles (user_id) "
            "VALUES (%s) RETURNING id, created_at, updated_at",
            (user_row[0],),
        ).fetchone()

        _assert_uuid_and_aware_timestamps(user_row)
        _assert_uuid_and_aware_timestamps(profile_row)


@pytest.mark.parametrize("username", ("", " ", "\t", "\n", " Alice", "Alice "))
def test_account_rejects_invalid_username(management_database_url, username):
    with (
        _connection(management_database_url) as conn,
        pytest.raises(psycopg.IntegrityError),
        conn.transaction(),
    ):
        conn.execute(
            "INSERT INTO operational.accounts (username, password_hash) "
            "VALUES (%s, %s)",
            (username, "test-hash-not-a-real-credential"),
        )


@pytest.mark.parametrize(
    ("column", "value"),
    (
        ("username", None),
        ("password_hash", None),
        ("password_hash", ""),
        ("password_hash", " "),
        ("password_hash", "\t"),
        ("password_hash", "\n"),
        ("status", None),
        ("status", "pending"),
    ),
)
def test_account_rejects_invalid_required_values(
    management_database_url,
    column,
    value,
):
    values = {
        "username": f"account-{uuid4()}",
        "password_hash": "test-hash-not-a-real-credential",
        "status": "active",
    }
    values[column] = value

    with (
        _connection(management_database_url) as conn,
        pytest.raises(psycopg.IntegrityError),
        conn.transaction(),
    ):
        conn.execute(
            "INSERT INTO operational.accounts "
            "(username, password_hash, status) VALUES (%s, %s, %s)",
            (values["username"], values["password_hash"], values["status"]),
        )


def test_account_username_is_case_insensitively_unique(management_database_url):
    with _connection(management_database_url) as conn:
        _insert_account(conn, username="Alice")
        with pytest.raises(psycopg.IntegrityError), conn.transaction():
            _insert_account(conn, username="alice")

        distinct_id = _insert_account(conn, username="Alicia")
        assert isinstance(distinct_id, UUID)


def test_account_accepts_disabled_status(management_database_url):
    with _connection(management_database_url) as conn:
        status = conn.execute(
            "INSERT INTO operational.accounts (username, password_hash, status) "
            "VALUES (%s, %s, %s) RETURNING status",
            (f"account-{uuid4()}", "test-hash-not-a-real-credential", "disabled"),
        ).fetchone()[0]

        assert status == "disabled"


@pytest.mark.parametrize("column", USER_TEXT_FIELDS)
@pytest.mark.parametrize("value", INVALID_TRIMMED_TEXT)
def test_user_rejects_invalid_required_text(
    management_database_url,
    column,
    value,
):
    with _connection(management_database_url) as conn:
        account_id = _insert_account(conn)
        values = {
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@example.test",
            "phone_number": "+970599000000",
            "country_of_residence": "Palestine",
        }
        values[column] = value
        query = sql.SQL(
            "INSERT INTO operational.users "
            "(account_id, first_name, last_name, email, phone_number, "
            "country_of_residence) VALUES (%s, %s, %s, %s, %s, %s)"
        )

        with pytest.raises(psycopg.IntegrityError), conn.transaction():
            conn.execute(
                query,
                (
                    account_id,
                    values["first_name"],
                    values["last_name"],
                    values["email"],
                    values["phone_number"],
                    values["country_of_residence"],
                ),
            )


@pytest.mark.parametrize("value", ("", " ", "\t", "\n", " UTC", "UTC "))
def test_user_rejects_invalid_supplied_timezone(management_database_url, value):
    with _connection(management_database_url) as conn:
        account_id = _insert_account(conn)
        with pytest.raises(psycopg.IntegrityError), conn.transaction():
            conn.execute(
                """
                INSERT INTO operational.users (
                    account_id, first_name, last_name, email, phone_number,
                    country_of_residence, timezone
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    account_id,
                    "Ada",
                    "Lovelace",
                    "ada@example.test",
                    "+970599000000",
                    "Palestine",
                    value,
                ),
            )


def test_user_accepts_null_timezone(management_database_url):
    with _connection(management_database_url) as conn:
        user_id = _insert_user(conn, _insert_account(conn))
        timezone = conn.execute(
            "UPDATE operational.users SET timezone = NULL WHERE id = %s "
            "RETURNING timezone",
            (user_id,),
        ).fetchone()[0]

        assert timezone is None


def test_user_rejects_null_or_duplicate_account(management_database_url):
    with _connection(management_database_url) as conn:
        account_id = _insert_account(conn)
        _insert_user(conn, account_id)

        with pytest.raises(psycopg.IntegrityError), conn.transaction():
            _insert_user(conn, account_id)

        with pytest.raises(psycopg.IntegrityError), conn.transaction():
            conn.execute(
                """
                INSERT INTO operational.users (
                    account_id, first_name, last_name, email, phone_number,
                    country_of_residence
                ) VALUES (NULL, 'Ada', 'Lovelace', 'ada@example.test',
                          '+970599000000', 'Palestine')
                """
            )


def test_user_rejects_nonexistent_account(management_database_url):
    with (
        _connection(management_database_url) as conn,
        pytest.raises(psycopg.IntegrityError),
        conn.transaction(),
    ):
        _insert_user(conn, uuid4())


def test_profile_has_empty_collections_and_nullable_text(management_database_url):
    with _connection(management_database_url) as conn:
        user_id = _insert_user(conn, _insert_account(conn))
        row = conn.execute(
            "INSERT INTO operational.professional_profiles "
            "(user_id, headline, professional_summary) VALUES (%s, NULL, NULL) "
            "RETURNING skills, experience, previous_projects, headline, "
            "professional_summary",
            (user_id,),
        ).fetchone()

        assert row == ([], [], [], None, None)


@pytest.mark.parametrize("column", ("headline", "professional_summary"))
@pytest.mark.parametrize("value", ("", " ", "\t", "\n", " value", "value "))
def test_profile_rejects_invalid_supplied_text(
    management_database_url,
    column,
    value,
):
    with _connection(management_database_url) as conn:
        user_id = _insert_user(conn, _insert_account(conn))
        query = sql.SQL(
            "INSERT INTO operational.professional_profiles (user_id, {}) "
            "VALUES (%s, %s)"
        ).format(sql.Identifier(column))

        with pytest.raises(psycopg.IntegrityError), conn.transaction():
            conn.execute(query, (user_id, value))


def test_profile_rejects_duplicate_or_nonexistent_user(management_database_url):
    with _connection(management_database_url) as conn:
        user_id = _insert_user(conn, _insert_account(conn))
        _insert_profile(conn, user_id)

        with pytest.raises(psycopg.IntegrityError), conn.transaction():
            _insert_profile(conn, user_id)

        with pytest.raises(psycopg.IntegrityError), conn.transaction():
            _insert_profile(conn, uuid4())


@pytest.mark.parametrize("column", COLLECTION_FIELDS)
@pytest.mark.parametrize(
    ("value", "as_json"),
    (
        (None, False),
        (None, True),
        ({}, True),
        (7, True),
        (["not-an-object"], True),
        ([[{"name": "nested"}]], True),
    ),
)
def test_profile_rejects_invalid_collection_shapes(
    management_database_url,
    column,
    value,
    as_json,
):
    with _connection(management_database_url) as conn:
        user_id = _insert_user(conn, _insert_account(conn))
        query = sql.SQL(
            "INSERT INTO operational.professional_profiles (user_id, {}) "
            "VALUES (%s, %s)"
        ).format(sql.Identifier(column))
        parameter = Jsonb(value) if as_json else value

        with pytest.raises(psycopg.IntegrityError), conn.transaction():
            conn.execute(query, (user_id, parameter))


@pytest.mark.parametrize("column", COLLECTION_FIELDS)
@pytest.mark.parametrize("value", ([], [{"arbitrary": "object"}]))
def test_profile_accepts_array_of_objects(
    management_database_url,
    column,
    value,
):
    with _connection(management_database_url) as conn:
        user_id = _insert_user(conn, _insert_account(conn))
        query = sql.SQL(
            "INSERT INTO operational.professional_profiles (user_id, {}) "
            "VALUES (%s, %s) RETURNING {}"
        ).format(sql.Identifier(column), sql.Identifier(column))

        stored = conn.execute(query, (user_id, Jsonb(value))).fetchone()[0]
        assert stored == value


def test_professional_collections_round_trip_through_jsonb(
    management_database_url,
):
    collections = ProfessionalCollections.model_validate(
        {
            "skills": [{"name": "Python"}, {"name": "PostgreSQL"}],
            "experience": [
                {
                    "organization": "Analytical Engines",
                    "role": "Programmer",
                    "summary": "Computed Bernoulli numbers",
                    "start_month": "1842-01",
                    "end_month": "1843-12",
                    "is_current": False,
                }
            ],
            "previous_projects": [
                {"name": "Note G", "description": "An algorithm for an engine"},
                {"name": "Translation", "description": "Added extensive notes"},
            ],
        }
    )
    dumped = collections.model_dump(mode="json")

    with _connection(management_database_url) as conn:
        user_id = _insert_user(conn, _insert_account(conn))
        stored = conn.execute(
            """
            INSERT INTO operational.professional_profiles (
                user_id, skills, experience, previous_projects
            ) VALUES (%s, %s, %s, %s)
            RETURNING skills, experience, previous_projects
            """,
            (
                user_id,
                Jsonb(dumped["skills"]),
                Jsonb(dumped["experience"]),
                Jsonb(dumped["previous_projects"]),
            ),
        ).fetchone()

    revalidated = ProfessionalCollections.model_validate(
        dict(zip(COLLECTION_FIELDS, stored, strict=True))
    )
    assert revalidated.model_dump(mode="json") == dumped


def test_parent_and_children_can_be_inserted_in_one_transaction(
    management_database_url,
):
    with _connection(management_database_url) as conn:
        account_id = _insert_account(conn)
        user_id = _insert_user(conn, account_id)
        profile_id = _insert_profile(conn, user_id)

        assert all(
            isinstance(value, UUID) for value in (account_id, user_id, profile_id)
        )


def test_deleting_referenced_account_or_user_is_rejected(management_database_url):
    with _connection(management_database_url) as conn:
        account_id = _insert_account(conn)
        user_id = _insert_user(conn, account_id)
        _insert_profile(conn, user_id)

        with pytest.raises(psycopg.IntegrityError), conn.transaction():
            conn.execute(
                "DELETE FROM operational.accounts WHERE id = %s", (account_id,)
            )

        with pytest.raises(psycopg.IntegrityError), conn.transaction():
            conn.execute("DELETE FROM operational.users WHERE id = %s", (user_id,))


def test_existing_match_references_management_user(management_database_url):
    with _connection(management_database_url) as conn:
        company_id = conn.execute(
            "INSERT INTO gold.company (domain, name) VALUES (%s, %s) RETURNING id",
            (f"schema-{uuid4()}.example", "Schema Test Company"),
        ).fetchone()[0]
        user_id = _insert_user(conn, _insert_account(conn))
        match_id = conn.execute(
            "INSERT INTO operational.match (user_id, company_id) "
            "VALUES (%s, %s) RETURNING id",
            (user_id, company_id),
        ).fetchone()[0]

        assert isinstance(match_id, UUID)
        with pytest.raises(psycopg.IntegrityError), conn.transaction():
            conn.execute(
                "INSERT INTO operational.match (user_id, company_id) VALUES (%s, %s)",
                (uuid4(), company_id),
            )


def test_out_of_scope_management_tables_are_absent(management_database_url):
    absent_tables = (
        "sessions",
        "offerings",
        "icps",
        "strategies",
        "normalized_profiles",
    )
    with psycopg.connect(management_database_url) as conn:
        found = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'operational' AND table_name = ANY(%s)",
            (list(absent_tables),),
        ).fetchall()

    assert found == []
