import logging

from huginn.elt.bronze.api_ingest_state import PostgresApiIngestState


class _FakeApiIngestRepository:
    """Hand-rolled `ApiIngestRepositoryPort` double, not a mocking
    framework (CLAUDE.md code standard 4), local to this file per
    BEST_PRACTICES.md section 7.1 (a one-off fixture belongs next to what
    uses it, not shared across test files).

    `PostgresApiIngestState` no longer opens a connection or issues SQL
    itself, so the boundary these tests exercise is the repository port:
    the class must delegate the lookup rather than carry its own copy of
    the query, and must open a repository scope to do it.
    """

    def __init__(self, lookup_result):
        self._lookup_result = lookup_result
        self.calls = []
        self.enter_count = 0
        self.exit_count = 0

    def __enter__(self):
        self.enter_count += 1
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.exit_count += 1
        return None

    def lookup_hash(self, source, stable_id):
        self.calls.append((source, stable_id))
        return self._lookup_result

    def write(self, source, stable_id, payload, content_hash, run_id):
        raise AssertionError("StatePort must never write")

    def touch(self, source, stable_id):
        raise AssertionError("StatePort must never touch")


def test_last_hash_returns_none_when_never_seen():
    state = PostgresApiIngestState(_FakeApiIngestRepository(lookup_result=None))

    result = state.last_hash("hn", "49522897")

    assert result is None


def test_last_hash_returns_stored_hash_when_row_exists():
    state = PostgresApiIngestState(_FakeApiIngestRepository(lookup_result="hash123"))

    result = state.last_hash("hn", "49522897")

    assert result == "hash123"


def test_last_hash_delegates_to_the_shared_repository_lookup():
    repository = _FakeApiIngestRepository(lookup_result=None)
    state = PostgresApiIngestState(repository)

    state.last_hash("hn", "49522897")

    # One delegated call, no second implementation of the same query: the
    # repository is the single owner of the bronze.api_ingest lookup that
    # PostgresApiIngestStore's write path also uses. The call happens
    # inside one repository scope, per the port's contract.
    assert repository.calls == [("hn", "49522897")]
    assert repository.enter_count == 1
    assert repository.exit_count == 1


def test_last_hash_logs_hit_at_debug_level(caplog):
    state = PostgresApiIngestState(_FakeApiIngestRepository(lookup_result="hash123"))

    with caplog.at_level(logging.DEBUG):
        state.last_hash("hn", "49522897")

    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.DEBUG
    assert "hit" in caplog.text
    assert "hn" in caplog.text
    assert "49522897" in caplog.text


def test_last_hash_logs_miss_at_debug_level(caplog):
    state = PostgresApiIngestState(_FakeApiIngestRepository(lookup_result=None))

    with caplog.at_level(logging.DEBUG):
        state.last_hash("hn", "49522897")

    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.DEBUG
    assert "miss" in caplog.text
