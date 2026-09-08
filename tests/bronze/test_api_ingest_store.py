from huginn.bronze.api_ingest_store import (
    ACTION_SKIP,
    ACTION_WRITE,
    decide_write_action,
)


def test_decide_write_action_writes_when_no_existing_row():
    assert decide_write_action(None, "abc123") == ACTION_WRITE


def test_decide_write_action_writes_when_hash_differs():
    assert decide_write_action("old_hash", "new_hash") == ACTION_WRITE


def test_decide_write_action_skips_when_hash_matches():
    assert decide_write_action("same_hash", "same_hash") == ACTION_SKIP
