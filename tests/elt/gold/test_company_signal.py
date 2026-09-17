from __future__ import annotations

from datetime import UTC, datetime

from huginn.elt.gold.company_signal import CompanySignalWriter
from huginn.elt.gold.models import ResolvedSignalForFact


class FakeCompanySignalRepository:
    def __init__(self, facts):
        self._facts = facts
        self.upserted = []
        self.enter_count = 0
        self.exit_count = 0

    def __enter__(self):
        self.enter_count += 1
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.exit_count += 1

    def read_signal_facts(self):
        return self._facts

    def upsert_signal(self, fact):
        self.upserted.append(fact)


def _fact(source_stable_id: str = "1", company_id: str = "c1") -> ResolvedSignalForFact:
    return ResolvedSignalForFact(
        company_id=company_id,
        source="hn",
        source_stable_id=source_stable_id,
        signal_type="hiring",
        source_url="https://example.invalid",
        stage=None,
        description="desc",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_write_all_writes_one_fact_per_signal():
    repo = FakeCompanySignalRepository(facts=[_fact("1"), _fact("2")])
    writer = CompanySignalWriter(repo)

    written = writer.write_all()

    assert written == 2
    assert repo.upserted == [_fact("1"), _fact("2")]


def test_write_all_does_not_collapse_multiple_signals_for_the_same_company():
    """Regression: unlike CompanyWriter, this writer stays at event grain,
    two signals for the same company_id both get their own fact row."""
    repo = FakeCompanySignalRepository(
        facts=[_fact("1", company_id="c1"), _fact("2", company_id="c1")]
    )
    writer = CompanySignalWriter(repo)

    written = writer.write_all()

    assert written == 2


def test_write_all_returns_zero_for_an_empty_batch():
    repo = FakeCompanySignalRepository(facts=[])
    writer = CompanySignalWriter(repo)

    assert writer.write_all() == 0
    assert repo.upserted == []


def test_write_all_opens_the_repository_scope_once_for_the_whole_batch():
    repo = FakeCompanySignalRepository(facts=[_fact("1"), _fact("2")])
    writer = CompanySignalWriter(repo)

    writer.write_all()

    assert repo.enter_count == 1
    assert repo.exit_count == 1
