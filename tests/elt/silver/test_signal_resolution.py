from __future__ import annotations

from datetime import UTC, datetime

import pytest

from huginn.elt.silver import signal_resolution
from huginn.elt.silver.models import StagedSignal
from huginn.elt.silver.resolution import KeyDerivation
from huginn.elt.silver.signal_resolution import (
    _NON_COMPANY_HOSTS,
    SignalResolver,
    resolve_signal,
    unresolved_placeholder_key,
)


def test_resolve_signal_normalizes_a_normalizable_domain(monkeypatch):
    """Derive a company key from a normalizable website domain."""
    monkeypatch.setattr(
        signal_resolution, "check_domain_reachable", lambda domain, timeout=5.0: True
    )

    key, confidence = resolve_signal("hn", "1", "https://www.acme.com/careers")

    assert key == "acme.com"
    assert confidence == KeyDerivation.DOMAIN_NORMALIZED


def test_resolve_signal_returns_unresolved_when_website_is_none():
    """Mark a signal without a website as unresolved."""
    key, confidence = resolve_signal("hn", "1", None)

    assert key == "unresolved:hn:1"
    assert confidence == KeyDerivation.UNRESOLVED


def test_resolve_signal_returns_unresolved_when_website_is_empty_string():
    """Mark a signal with an empty website as unresolved."""
    key, confidence = resolve_signal("hn", "1", "")

    assert key == "unresolved:hn:1"
    assert confidence == KeyDerivation.UNRESOLVED


def test_resolve_signal_rejects_a_denylisted_ats_host():
    """Reject an applicant-tracking host as a company key."""
    key, confidence = resolve_signal(
        "hn", "1", "https://acme.bamboohr.com/jobs/view/42"
    )

    assert key == "unresolved:hn:1"
    assert confidence == KeyDerivation.UNRESOLVED


def test_resolve_signal_rejects_a_denylisted_platform_host():
    """Reject a shared platform host as a company key."""
    key, confidence = resolve_signal("yc", "7", "https://www.ycombinator.com/companies")

    assert key == "unresolved:yc:7"
    assert confidence == KeyDerivation.UNRESOLVED


def test_resolve_signal_rejects_a_subdomain_of_a_denylisted_host():
    """Reject subdomains belonging to a denylisted host."""
    key, confidence = resolve_signal("hn", "2", "https://boards.greenhouse.io/acme")

    assert key == "unresolved:hn:2"
    assert confidence == KeyDerivation.UNRESOLVED


def test_resolve_signal_rejects_every_denylisted_host():
    """Keep every configured non-company host unresolved."""
    for host in _NON_COMPANY_HOSTS:
        key, confidence = resolve_signal("hn", "1", f"https://{host}/careers")

        assert confidence == KeyDerivation.UNRESOLVED, host
        assert key == "unresolved:hn:1", host


def test_resolve_signal_still_normalizes_a_real_company_domain(monkeypatch):
    """Regression check for the denylist: a company domain that merely
    resembles a denylisted one, or contains it as a non-suffix substring,
    must still auto-match.
    """
    monkeypatch.setattr(
        signal_resolution, "check_domain_reachable", lambda domain, timeout=5.0: True
    )

    for website in (
        "https://modash.io",
        "https://www.acme.com/careers",
        "https://notgreenhouse.io",
        "https://greenhouse.io.acme.com",
        "https://careers.acme.com",
    ):
        _, confidence = resolve_signal("hn", "1", website)

        assert confidence == KeyDerivation.DOMAIN_NORMALIZED, website


def test_unresolved_placeholder_key_is_scoped_by_source_and_stable_id():
    assert unresolved_placeholder_key("hn", "1") != unresolved_placeholder_key(
        "yc", "1"
    )
    assert unresolved_placeholder_key("hn", "1") != unresolved_placeholder_key(
        "hn", "2"
    )


def _staged_signal(
    source: str,
    stable_id: str,
    website: str | None,
    *,
    company_status: str | None = None,
    team_size: int | None = None,
    industries: tuple[str, ...] | None = None,
    all_locations: str | None = None,
    former_names: tuple[str, ...] | None = None,
    batch: str | None = None,
) -> StagedSignal:
    return StagedSignal(
        source=source,
        stable_id=stable_id,
        company_name_raw="Acme",
        website=website,
        signal_type="hiring",
        stage=None,
        description="",
        occurred_on=datetime.fromtimestamp(0, tz=UTC),
        url="https://example.invalid",
        company_status=company_status,
        team_size=team_size,
        industries=industries,
        all_locations=all_locations,
        former_names=former_names,
        batch=batch,
    )


@pytest.fixture(autouse=True)
def _reachable_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Answer every reachability check positively unless a test says
    otherwise.

    `resolve_signal` calls `check_domain_reachable`, which opens a socket
    (Jira KAN-62). Without this, any test whose staged signal carries a
    derivable domain would make real network calls, so a green unit suite
    would depend on someone else's uptime. A test that cares about the
    reachability decision still installs its own `monkeypatch.setattr`,
    which lands after this fixture and wins.
    """
    monkeypatch.setattr(
        signal_resolution, "check_domain_reachable", lambda domain, timeout=5.0: True
    )


class FakeSignalResolutionRepository:
    def __init__(
        self, hn_postings: list[StagedSignal], yc_listings: list[StagedSignal]
    ) -> None:
        self._hn_postings = hn_postings
        self._yc_listings = yc_listings
        self.upserted = []
        self.enter_count = 0
        self.exit_count = 0
        self.calls: list[str] = []

    def __enter__(self):
        self.enter_count += 1
        self.calls.append("enter")
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.exit_count += 1
        self.calls.append("exit")

    def read_hn_postings(self) -> list[StagedSignal]:
        self.calls.append("read_hn")
        return self._hn_postings

    def read_yc_listings(self) -> list[StagedSignal]:
        self.calls.append("read_yc")
        return self._yc_listings

    def upsert(self, record) -> None:
        self.calls.append("upsert")
        self.upserted.append(record)


def test_resolve_all_combines_hn_and_yc_staged_signals_into_the_upsert_count(
    monkeypatch,
):
    monkeypatch.setattr(
        signal_resolution, "check_domain_reachable", lambda domain, timeout=5.0: True
    )

    repository = FakeSignalResolutionRepository(
        hn_postings=[_staged_signal("hn", "1", "https://acme.com")],
        yc_listings=[
            _staged_signal("yc", "2", "https://getnao.io"),
            _staged_signal("yc", "3", None),
        ],
    )
    resolver = SignalResolver(repository)

    resolver.resolve_all()

    assert len(repository.upserted) == 3


def test_resolve_all_upserts_a_record_wired_to_what_resolve_signal_computed(
    monkeypatch,
):
    """Persist the key and derivation status computed for each signal."""
    monkeypatch.setattr(
        signal_resolution, "check_domain_reachable", lambda domain, timeout=5.0: True
    )

    repository = FakeSignalResolutionRepository(
        hn_postings=[_staged_signal("hn", "1", "https://acme.com")],
        yc_listings=[_staged_signal("yc", "2", None)],
    )
    resolver = SignalResolver(repository)

    resolver.resolve_all()

    by_stable_id = {record.source_stable_id: record for record in repository.upserted}
    matched = by_stable_id["1"]
    assert matched.resolved_company_key == "acme.com"
    assert matched.key_derivation == KeyDerivation.DOMAIN_NORMALIZED

    unmatched = by_stable_id["2"]
    assert unmatched.resolved_company_key == "unresolved:yc:2"
    assert unmatched.key_derivation == KeyDerivation.UNRESOLVED


def test_resolve_all_returns_the_total_written_count(monkeypatch):
    monkeypatch.setattr(
        signal_resolution, "check_domain_reachable", lambda domain, timeout=5.0: True
    )

    repository = FakeSignalResolutionRepository(
        hn_postings=[_staged_signal("hn", "1", "https://acme.com")],
        yc_listings=[_staged_signal("yc", "2", None)],
    )
    resolver = SignalResolver(repository)

    written = resolver.resolve_all()

    assert written == 2


def test_resolve_all_opens_the_repository_scope_twice_read_then_write(monkeypatch):
    """ADR-0006: reads and writes now open two separate connection scopes,
    not one, so resolve_signal()'s network call (KAN-62) never runs while
    a database connection is held open. Sharing a single scope across the
    whole batch, as this orchestrator did before ADR-0006, is exactly what
    that ADR moved away from."""
    monkeypatch.setattr(
        signal_resolution, "check_domain_reachable", lambda domain, timeout=5.0: True
    )

    repository = FakeSignalResolutionRepository(
        hn_postings=[_staged_signal("hn", "1", "https://acme.com")],
        yc_listings=[_staged_signal("yc", "2", None)],
    )
    resolver = SignalResolver(repository)

    resolver.resolve_all()

    assert repository.enter_count == 2
    assert repository.exit_count == 2


def test_resolve_all_completes_every_read_before_opening_the_write_scope(monkeypatch):
    """ADR-0006: no upsert may happen inside the read scope, and no read
    may happen inside the write scope, only sequential
    enter/read.../exit/enter/upsert.../exit."""
    monkeypatch.setattr(
        signal_resolution, "check_domain_reachable", lambda domain, timeout=5.0: True
    )

    repository = FakeSignalResolutionRepository(
        hn_postings=[_staged_signal("hn", "1", "https://acme.com")],
        yc_listings=[_staged_signal("yc", "2", None)],
    )
    resolver = SignalResolver(repository)

    resolver.resolve_all()

    second_enter_index = [
        index for index, call in enumerate(repository.calls) if call == "enter"
    ][1]
    read_indices = [
        index
        for index, call in enumerate(repository.calls)
        if call in ("read_hn", "read_yc")
    ]
    upsert_indices = [
        index for index, call in enumerate(repository.calls) if call == "upsert"
    ]
    assert all(index < second_enter_index for index in read_indices)
    assert all(index > second_enter_index for index in upsert_indices)


def test_resolve_all_runs_every_reachability_check_with_no_scope_open(monkeypatch):
    """ADR-0006's actual point: resolve_signal()'s network call must run
    strictly between the read scope's exit and the write scope's enter,
    never while either connection scope is open. Recording enter/read/
    upsert/exit alone (the previous test) cannot tell an implementation
    that does the checks inside the read scope apart from one that does
    them in the gap; recording the check calls into the same ordered
    sequence closes that gap."""
    repository = FakeSignalResolutionRepository(
        hn_postings=[_staged_signal("hn", "1", "https://acme.com")],
        yc_listings=[_staged_signal("yc", "2", "https://getnao.io")],
    )

    def fake_check(domain, timeout=5.0):
        repository.calls.append("check")
        return True

    monkeypatch.setattr(signal_resolution, "check_domain_reachable", fake_check)
    resolver = SignalResolver(repository)

    resolver.resolve_all()

    first_exit_index = repository.calls.index("exit")
    second_enter_index = [
        index for index, call in enumerate(repository.calls) if call == "enter"
    ][1]
    check_indices = [
        index for index, call in enumerate(repository.calls) if call == "check"
    ]
    assert len(check_indices) == 2
    assert all(first_exit_index < index < second_enter_index for index in check_indices)


def test_resolve_signal_returns_unresolved_when_domain_is_not_reachable(
    monkeypatch,
):
    monkeypatch.setattr(
        signal_resolution, "check_domain_reachable", lambda domain, timeout=5.0: False
    )

    key, confidence = resolve_signal("hn", "1", "https://www.acme.com/careers")

    assert key == "unresolved:hn:1"
    assert confidence == KeyDerivation.UNRESOLVED


def test_resolve_signal_normalizes_when_domain_is_reachable(monkeypatch):
    monkeypatch.setattr(
        signal_resolution, "check_domain_reachable", lambda domain, timeout=5.0: True
    )

    key, confidence = resolve_signal("hn", "1", "https://www.acme.com/careers")

    assert key == "acme.com"
    assert confidence == KeyDerivation.DOMAIN_NORMALIZED


def test_resolve_signal_checks_reachability_on_the_normalized_domain(monkeypatch):
    """The domain passed to check_domain_reachable must be the normalized
    host (no scheme/path), not the raw website string."""
    seen = {}

    def fake_check(domain, timeout=5.0):
        seen["domain"] = domain
        return True

    monkeypatch.setattr(signal_resolution, "check_domain_reachable", fake_check)

    resolve_signal("hn", "1", "https://www.acme.com/careers")

    assert seen["domain"] == "acme.com"


def test_resolve_signal_does_not_check_reachability_for_a_denylisted_host(
    monkeypatch,
):
    """A denylisted host is rejected before reachability is ever checked,
    no network call should be attempted for it at all."""

    def fail_if_called(domain, timeout=5.0):
        raise AssertionError("check_domain_reachable should not be called")

    monkeypatch.setattr(signal_resolution, "check_domain_reachable", fail_if_called)

    key, confidence = resolve_signal(
        "hn", "1", "https://acme.bamboohr.com/jobs/view/42"
    )

    assert confidence == KeyDerivation.UNRESOLVED


def test_resolve_signal_rejects_denylisted_host_with_trailing_dot(monkeypatch):
    """Trailing dot (DNS root label) on a denylisted domain must not bypass
    the denylist. See Jira KAN-69 for the false-merge bug this prevents."""

    def fail_if_called(domain, timeout=5.0):
        raise AssertionError("check_domain_reachable should not be called")

    monkeypatch.setattr(signal_resolution, "check_domain_reachable", fail_if_called)

    key, confidence = resolve_signal(
        "hn", "1", "https://acme.bamboohr.com./jobs/view/42"
    )

    assert key == "unresolved:hn:1"
    assert confidence == KeyDerivation.UNRESOLVED


def test_resolve_all_carries_company_status_and_team_size_into_the_upserted_record():
    """Resolution is identity, but it is also a copy: a field the YC parser
    read must still be there once the signal reaches resolved_signals.

    The separate parser test cannot catch a drop here, because the failure
    mode is a column parsed correctly and then silently absent from the
    record that gets persisted, which is invisible until Gold reads it.
    """
    repository = FakeSignalResolutionRepository(
        hn_postings=[],
        yc_listings=[
            _staged_signal(
                "yc",
                "2",
                "https://getnao.io",
                company_status="Active",
                team_size=50,
            )
        ],
    )
    resolver = SignalResolver(repository)

    resolver.resolve_all()

    record = repository.upserted[0]
    assert record.company_status == "Active"
    assert record.team_size == 50


def test_resolve_all_leaves_profile_fields_none_for_a_source_that_lacks_them():
    """HN's freeform comments carry no registry status and no headcount, so
    resolution must pass through NULL rather than defaulting one in.
    """
    repository = FakeSignalResolutionRepository(
        hn_postings=[_staged_signal("hn", "1", "https://acme.com")],
        yc_listings=[],
    )
    resolver = SignalResolver(repository)

    resolver.resolve_all()

    record = repository.upserted[0]
    assert record.company_status is None
    assert record.team_size is None


def test_resolve_all_preserves_a_zero_headcount():
    """0 must survive as 0. Coercing it to None here would erase the only
    signal that distinguishes a reported pre-first-hire count from a
    genuinely unknown one, and would silently move those companies out of
    the lowest band.
    """
    repository = FakeSignalResolutionRepository(
        hn_postings=[],
        yc_listings=[
            _staged_signal(
                "yc", "2", "https://getnao.io", company_status="Active", team_size=0
            )
        ],
    )
    resolver = SignalResolver(repository)

    resolver.resolve_all()

    assert repository.upserted[0].team_size == 0


def test_resolve_all_carries_industries_and_all_locations_into_the_record():
    """Same copy-not-drop obligation as status and headcount: Gold reads
    business_sector and country from resolved_signals and nowhere else, so
    a drop here empties three gold.company columns at once.
    """
    repository = FakeSignalResolutionRepository(
        hn_postings=[],
        yc_listings=[
            _staged_signal(
                "yc",
                "2",
                "https://getnao.io",
                industries=("B2B", "Fintech"),
                all_locations="Berlin, Germany; Remote",
            )
        ],
    )

    SignalResolver(repository).resolve_all()

    record = repository.upserted[0]
    assert record.industries == ("B2B", "Fintech")
    assert record.all_locations == "Berlin, Germany; Remote"


def test_resolve_all_leaves_sector_and_location_none_for_hn_rows():
    """HN has neither, and writing anything here would be another source's
    value landing on an HN row rather than a missing value.
    """
    repository = FakeSignalResolutionRepository(
        hn_postings=[_staged_signal("hn", "1", "https://acme.com")],
        yc_listings=[],
    )

    SignalResolver(repository).resolve_all()

    record = repository.upserted[0]
    assert record.industries is None
    assert record.all_locations is None


def test_resolve_all_carries_former_names_and_batch_into_the_record():
    """Both are read from staged signals by nothing yet, which is exactly
    why a copy dropped here would go unnoticed: former_names is waiting on
    the KAN-4 matcher and batch on nothing. Losing either is silent, so the
    obligation is pinned here rather than left to inspection.
    """
    repository = FakeSignalResolutionRepository(
        hn_postings=[],
        yc_listings=[
            _staged_signal(
                "yc",
                "2",
                "https://getnao.io",
                former_names=("ZenPayroll", "Zen Payroll"),
                batch="Winter 2022",
            )
        ],
    )

    SignalResolver(repository).resolve_all()

    record = repository.upserted[0]
    assert record.former_names == ("ZenPayroll", "Zen Payroll")
    assert record.batch == "Winter 2022"


def test_resolve_all_leaves_former_names_and_batch_none_for_hn_rows():
    repository = FakeSignalResolutionRepository(
        hn_postings=[_staged_signal("hn", "1", "https://acme.com")],
        yc_listings=[],
    )

    SignalResolver(repository).resolve_all()

    record = repository.upserted[0]
    assert record.former_names is None
    assert record.batch is None
