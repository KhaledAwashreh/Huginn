from __future__ import annotations

from huginn.silver.manual_review import NO_SCORE_COMPUTED, ManualReviewQueuer


class FakeManualReviewRepository:
    def __init__(
        self,
        unmatched: list[tuple[str, str]],
        insert_results: dict[tuple[str, str], bool] | None = None,
    ) -> None:
        self._unmatched = unmatched
        self._insert_results = insert_results or {}
        self.insert_calls: list[tuple[str, str, int]] = []
        self.enter_count = 0
        self.exit_count = 0

    def __enter__(self):
        self.enter_count += 1
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.exit_count += 1

    def read_unmatched(self) -> list[tuple[str, str]]:
        return self._unmatched

    def insert_if_new(
        self, resolved_signal_id: str, candidate_company_key: str, match_score: int
    ) -> bool:
        self.insert_calls.append(
            (resolved_signal_id, candidate_company_key, match_score)
        )
        return self._insert_results.get(
            (resolved_signal_id, candidate_company_key), True
        )


def test_queue_unmatched_calls_insert_if_new_once_per_unmatched_row_with_no_score_computed():
    repository = FakeManualReviewRepository(
        [("signal-1", "unresolved:hn:1"), ("signal-2", "unresolved:yc:2")]
    )
    queuer = ManualReviewQueuer(repository)

    queuer.queue_unmatched()

    assert repository.insert_calls == [
        ("signal-1", "unresolved:hn:1", NO_SCORE_COMPUTED),
        ("signal-2", "unresolved:yc:2", NO_SCORE_COMPUTED),
    ]


def test_queue_unmatched_returns_only_the_count_of_newly_inserted_rows():
    repository = FakeManualReviewRepository(
        [("signal-1", "unresolved:hn:1"), ("signal-2", "unresolved:yc:2")],
        insert_results={
            ("signal-1", "unresolved:hn:1"): False,
            ("signal-2", "unresolved:yc:2"): True,
        },
    )
    queuer = ManualReviewQueuer(repository)

    written = queuer.queue_unmatched()

    assert written == 1


def test_queue_unmatched_opens_the_repository_scope_once_for_the_whole_batch():
    """Regression check: the batch must share one connection scope rather
    than opening one per record."""
    repository = FakeManualReviewRepository(
        [("signal-1", "unresolved:hn:1"), ("signal-2", "unresolved:yc:2")]
    )
    queuer = ManualReviewQueuer(repository)

    queuer.queue_unmatched()

    assert repository.enter_count == 1
    assert repository.exit_count == 1
