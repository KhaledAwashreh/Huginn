from __future__ import annotations

from datetime import UTC, datetime

from huginn.silver.models import StagedSignal
from huginn.silver.resolution import MatchConfidence
from huginn.silver.signal_resolution import (
    _NON_COMPANY_HOSTS,
    SignalResolver,
    resolve_signal,
    unresolved_placeholder_key,
)


def test_resolve_signal_auto_matches_a_normalizable_domain():
    key, confidence = resolve_signal("hn", "1", "https://www.acme.com/careers")

    assert key == "acme.com"
    assert confidence == MatchConfidence.AUTO_MATCHED


def test_resolve_signal_returns_no_existing_match_when_website_is_none():
    key, confidence = resolve_signal("hn", "1", None)

    assert key == "unresolved:hn:1"
    assert confidence == MatchConfidence.NO_EXISTING_MATCH


def test_resolve_signal_returns_no_existing_match_when_website_is_empty_string():
    key, confidence = resolve_signal("hn", "1", "")

    assert key == "unresolved:hn:1"
    assert confidence == MatchConfidence.NO_EXISTING_MATCH


def test_resolve_signal_rejects_a_denylisted_ats_host():
    key, confidence = resolve_signal(
        "hn", "1", "https://acme.bamboohr.com/jobs/view/42"
    )

    assert key == "unresolved:hn:1"
    assert confidence == MatchConfidence.NO_EXISTING_MATCH


def test_resolve_signal_rejects_a_denylisted_platform_host():
    key, confidence = resolve_signal("yc", "7", "https://www.ycombinator.com/companies")

    assert key == "unresolved:yc:7"
    assert confidence == MatchConfidence.NO_EXISTING_MATCH


def test_resolve_signal_rejects_a_subdomain_of_a_denylisted_host():
    key, confidence = resolve_signal("hn", "2", "https://boards.greenhouse.io/acme")

    assert key == "unresolved:hn:2"
    assert confidence == MatchConfidence.NO_EXISTING_MATCH


def test_resolve_signal_rejects_every_denylisted_host():
    for host in _NON_COMPANY_HOSTS:
        key, confidence = resolve_signal("hn", "1", f"https://{host}/careers")

        assert confidence == MatchConfidence.NO_EXISTING_MATCH, host
        assert key == "unresolved:hn:1", host


def test_resolve_signal_still_auto_matches_a_real_company_domain():
    """Regression check for the denylist: a company domain that merely
    resembles a denylisted one, or contains it as a non-suffix substring,
    must still auto-match.
    """
    for website in (
        "https://modash.io",
        "https://www.acme.com/careers",
        "https://notgreenhouse.io",
        "https://greenhouse.io.acme.com",
        "https://careers.acme.com",
    ):
        _, confidence = resolve_signal("hn", "1", website)

        assert confidence == MatchConfidence.AUTO_MATCHED, website


def test_unresolved_placeholder_key_is_scoped_by_source_and_stable_id():
    assert unresolved_placeholder_key("hn", "1") != unresolved_placeholder_key(
        "yc", "1"
    )
    assert unresolved_placeholder_key("hn", "1") != unresolved_placeholder_key(
        "hn", "2"
    )


def _staged_signal(source: str, stable_id: str, website: str | None) -> StagedSignal:
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

    def __enter__(self):
        self.enter_count += 1
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.exit_count += 1

    def read_hn_postings(self) -> list[StagedSignal]:
        return self._hn_postings

    def read_yc_listings(self) -> list[StagedSignal]:
        return self._yc_listings

    def upsert(self, record) -> None:
        self.upserted.append(record)


def test_resolve_all_combines_hn_and_yc_staged_signals_into_the_upsert_count():
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


def test_resolve_all_upserts_a_record_wired_to_what_resolve_signal_computed():
    repository = FakeSignalResolutionRepository(
        hn_postings=[_staged_signal("hn", "1", "https://acme.com")],
        yc_listings=[_staged_signal("yc", "2", None)],
    )
    resolver = SignalResolver(repository)

    resolver.resolve_all()

    by_stable_id = {record.source_stable_id: record for record in repository.upserted}
    matched = by_stable_id["1"]
    assert matched.resolved_company_key == "acme.com"
    assert matched.match_confidence == MatchConfidence.AUTO_MATCHED

    unmatched = by_stable_id["2"]
    assert unmatched.resolved_company_key == "unresolved:yc:2"
    assert unmatched.match_confidence == MatchConfidence.NO_EXISTING_MATCH


def test_resolve_all_returns_the_total_written_count():
    repository = FakeSignalResolutionRepository(
        hn_postings=[_staged_signal("hn", "1", "https://acme.com")],
        yc_listings=[_staged_signal("yc", "2", None)],
    )
    resolver = SignalResolver(repository)

    written = resolver.resolve_all()

    assert written == 2


def test_resolve_all_opens_the_repository_scope_once_for_the_whole_batch():
    """Regression check: the batch must share one connection scope rather
    than opening one per record."""
    repository = FakeSignalResolutionRepository(
        hn_postings=[_staged_signal("hn", "1", "https://acme.com")],
        yc_listings=[_staged_signal("yc", "2", None)],
    )
    resolver = SignalResolver(repository)

    resolver.resolve_all()

    assert repository.enter_count == 1
    assert repository.exit_count == 1
