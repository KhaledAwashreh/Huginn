from __future__ import annotations

from datetime import UTC, datetime

from huginn.elt.gold.company import CompanyWriter, write_company
from huginn.elt.gold.models import DomainNormalizedSignal


class FakeCompanyRepository:
    """In-memory `CompanyRepositoryPort` test double."""

    def __init__(self, signals, companies=None):
        self._signals = signals
        self._companies = companies or {}
        self.upserted = []
        self.history_inserted = []
        self.enter_count = 0
        self.exit_count = 0

    def __enter__(self):
        self.enter_count += 1
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.exit_count += 1

    def read_domain_normalized_signals(self):
        """Return the domain-normalized signals configured for this fake."""
        return self._signals

    def get_company(self, domain):
        return self._companies.get(domain)

    def upsert_company(self, domain, new_values, bump_current_since):
        self.upserted.append((domain, new_values, bump_current_since))

    def insert_history(self, company_id, domain, snapshot, valid_from):
        self.history_inserted.append((company_id, domain, snapshot, valid_from))


def _signal(domain: str, name: str) -> DomainNormalizedSignal:
    """Build the Gold input shape used by CompanyWriter tests."""
    return DomainNormalizedSignal(domain=domain, company_name_raw=name)


def test_write_company_inserts_a_new_company_on_first_occurrence():
    repo = FakeCompanyRepository(signals=[])

    write_company(repo, "acme.com", {"name": "Acme"})

    assert repo.upserted == [("acme.com", {"name": "Acme"}, False)]
    assert repo.history_inserted == []


def test_write_company_updates_name_with_no_history_when_no_type_2_field_present():
    repo = FakeCompanyRepository(
        signals=[],
        companies={
            "acme.com": {
                "id": "c1",
                "current_since": datetime(2026, 1, 1, tzinfo=UTC),
            }
        },
    )

    write_company(repo, "acme.com", {"name": "Acme Robotics"})

    assert repo.upserted == [("acme.com", {"name": "Acme Robotics"}, False)]
    assert repo.history_inserted == []


def test_write_company_writes_history_when_a_type_2_field_changes_on_an_existing_row():
    repo = FakeCompanyRepository(
        signals=[],
        companies={
            "acme.com": {
                "id": "c1",
                "icp_filter_pass": False,
                "current_since": datetime(2026, 1, 1, tzinfo=UTC),
            }
        },
    )

    write_company(repo, "acme.com", {"icp_filter_pass": True})

    assert repo.upserted[0][2] is True
    assert len(repo.history_inserted) == 1
    company_id, domain, snapshot, valid_from = repo.history_inserted[0]
    assert company_id == "c1"
    assert domain == "acme.com"
    assert snapshot["icp_filter_pass"] is False
    assert valid_from == datetime(2026, 1, 1, tzinfo=UTC)


def test_write_company_never_writes_history_on_first_occurrence_even_if_a_type_2_key_is_present():
    """Regression: apply_company_update can't tell "no row" apart from "row
    exists but the field was never set", so a Type 2 key in new_values must
    not trigger history when current is None. There is no prior version to
    supersede on first occurrence, and gold.company_history.company_id is
    NOT NULL (current.get("id") would be None here).
    """
    repo = FakeCompanyRepository(signals=[])

    write_company(repo, "acme.com", {"icp_filter_pass": True})

    assert repo.history_inserted == []


def test_write_all_processes_every_domain_normalized_signal():
    """Write each distinct domain-normalized signal in the batch."""
    repo = FakeCompanyRepository(
        signals=[_signal("acme.com", "Acme"), _signal("getnao.io", "Nao")]
    )
    writer = CompanyWriter(repo)

    written = writer.write_all()

    assert written == 2
    assert {domain for domain, _, _ in repo.upserted} == {"acme.com", "getnao.io"}


def test_write_all_upserts_domain_and_name_from_the_signal():
    repo = FakeCompanyRepository(signals=[_signal("acme.com", "Acme")])
    writer = CompanyWriter(repo)

    writer.write_all()

    assert repo.upserted == [("acme.com", {"name": "Acme"}, False)]


def test_write_all_collapses_multiple_signals_for_the_same_domain_into_one_write():
    """Regression: resolved_signals is event grain, so the same domain can
    appear in many rows. Only one write_company call (keeping the last-
    resolved name) should happen per domain, not one per event row.
    """
    repo = FakeCompanyRepository(
        signals=[
            _signal("acme.com", "Acme Old Name"),
            _signal("acme.com", "Acme New Name"),
        ]
    )
    writer = CompanyWriter(repo)

    written = writer.write_all()

    assert written == 1
    assert repo.upserted == [("acme.com", {"name": "Acme New Name"}, False)]


def test_write_all_opens_the_repository_scope_once_for_the_whole_batch():
    repo = FakeCompanyRepository(
        signals=[_signal("acme.com", "Acme"), _signal("getnao.io", "Nao")]
    )
    writer = CompanyWriter(repo)

    writer.write_all()

    assert repo.enter_count == 1
    assert repo.exit_count == 1
