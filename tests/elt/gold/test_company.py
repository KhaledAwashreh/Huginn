from __future__ import annotations

from datetime import UTC, datetime

from huginn.elt.gold.company import (
    CompanyWriter,
    parse_all_locations,
    team_size_to_scale,
    write_company,
)
from huginn.elt.gold.models import DomainNormalizedSignal
from huginn.elt.gold.repositories.company_repository import (
    _COMPANY_COLUMNS,
    build_upsert_query,
)


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


def _signal(
    domain: str,
    name: str,
    stage: str | None = None,
    company_status: str | None = None,
    team_size: int | None = None,
    industries: list[str] | None = None,
    all_locations: str | None = None,
    batch: str | None = None,
) -> DomainNormalizedSignal:
    """Build the Gold input shape used by CompanyWriter tests."""
    return DomainNormalizedSignal(
        domain=domain,
        company_name_raw=name,
        stage=stage,
        company_status=company_status,
        team_size=team_size,
        industries=industries,
        all_locations=all_locations,
        batch=batch,
    )


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
                "business_sector": ["fintech"],
                "current_since": datetime(2026, 1, 1, tzinfo=UTC),
            }
        },
    )

    write_company(repo, "acme.com", {"business_sector": ["b2b", "fintech"]})

    assert repo.upserted[0][2] is True
    assert len(repo.history_inserted) == 1
    company_id, domain, snapshot, valid_from = repo.history_inserted[0]
    assert company_id == "c1"
    assert domain == "acme.com"
    assert snapshot["business_sector"] == ["fintech"]
    assert valid_from == datetime(2026, 1, 1, tzinfo=UTC)


def test_write_company_never_writes_history_on_first_occurrence_even_if_a_type_2_key_is_present():
    """Regression: apply_company_update can't tell "no row" apart from "row
    exists but the field was never set", so a Type 2 key in new_values must
    not trigger history when current is None. There is no prior version to
    supersede on first occurrence, and gold.company_history.company_id is
    NOT NULL (current.get("id") would be None here).
    """
    repo = FakeCompanyRepository(signals=[])

    write_company(repo, "acme.com", {"business_sector": ["b2b", "fintech"]})

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


def test_write_all_carries_stage_from_the_signal():
    repo = FakeCompanyRepository(signals=[_signal("acme.com", "Acme", stage="Early")])
    writer = CompanyWriter(repo)

    writer.write_all()

    assert repo.upserted == [("acme.com", {"name": "Acme", "stage": "Early"}, False)]


def test_write_all_keeps_a_known_stage_when_a_later_signal_has_none():
    """Regression: every HN signal carries stage=None by construction
    (silver/hn_staging.py), so a plain last-row-wins collapse erases a YC
    company's stage whenever an HN signal for the same domain is read
    after it. Absence means "this source does not know", not "unknown".
    """
    repo = FakeCompanyRepository(
        signals=[
            _signal("acme.com", "Acme", stage="Early"),
            _signal("acme.com", "Acme", stage=None),
        ]
    )
    writer = CompanyWriter(repo)

    written = writer.write_all()

    assert written == 1
    assert repo.upserted == [("acme.com", {"name": "Acme", "stage": "Early"}, False)]


def test_write_all_keeps_a_known_stage_when_an_earlier_signal_had_none():
    repo = FakeCompanyRepository(
        signals=[
            _signal("acme.com", "Acme", stage=None),
            _signal("acme.com", "Acme", stage="Growth"),
        ]
    )
    writer = CompanyWriter(repo)

    writer.write_all()

    assert repo.upserted == [("acme.com", {"name": "Acme", "stage": "Growth"}, False)]


def test_write_all_prefers_the_latest_known_stage():
    repo = FakeCompanyRepository(
        signals=[
            _signal("acme.com", "Acme", stage="Early"),
            _signal("acme.com", "Acme", stage="Growth"),
        ]
    )
    writer = CompanyWriter(repo)

    writer.write_all()

    assert repo.upserted == [("acme.com", {"name": "Acme", "stage": "Growth"}, False)]


def test_write_all_omits_stage_entirely_when_no_signal_carries_one():
    """Omitting the key leaves gold.company.stage untouched on re-run,
    rather than writing NULL over a value some earlier run established.
    """
    repo = FakeCompanyRepository(signals=[_signal("acme.com", "Acme", stage=None)])
    writer = CompanyWriter(repo)

    writer.write_all()

    assert repo.upserted == [("acme.com", {"name": "Acme"}, False)]


def test_team_size_to_scale_returns_none_for_a_missing_headcount():
    assert team_size_to_scale(None) is None


def test_team_size_to_scale_folds_zero_into_the_lowest_band():
    """Confirmed live: 133 YC rows report team_size=0, all Early stage,
    all with a populated batch and industry, 41 of them Active. Reads as
    pre-first-hire, a real small size, not a missing value.
    """
    assert team_size_to_scale(0) == "0-10"


def test_team_size_to_scale_boundaries_are_inclusive_at_the_top():
    assert team_size_to_scale(1) == "0-10"
    assert team_size_to_scale(10) == "0-10"
    assert team_size_to_scale(11) == "11-100"
    assert team_size_to_scale(100) == "11-100"
    assert team_size_to_scale(101) == "101-1000"
    assert team_size_to_scale(1000) == "101-1000"
    assert team_size_to_scale(1001) == "1001+"


def test_team_size_to_scale_covers_the_real_observed_extremes():
    """Real values from the live directory, not invented ones."""
    assert team_size_to_scale(2) == "0-10"
    assert team_size_to_scale(227) == "101-1000"
    assert team_size_to_scale(7000) == "1001+"
    assert team_size_to_scale(10000) == "1001+"


def test_write_all_derives_company_scale_from_team_size():
    repo = FakeCompanyRepository(signals=[_signal("acme.com", "Acme", team_size=120)])
    writer = CompanyWriter(repo)

    writer.write_all()

    assert repo.upserted == [
        ("acme.com", {"name": "Acme", "company_scale": "101-1000"}, False)
    ]


def test_write_all_carries_company_status_from_the_signal():
    repo = FakeCompanyRepository(
        signals=[_signal("acme.com", "Acme", company_status="Public")]
    )
    writer = CompanyWriter(repo)

    writer.write_all()

    assert repo.upserted == [
        ("acme.com", {"name": "Acme", "company_status": "Public"}, False)
    ]


def test_write_all_keeps_a_known_company_status_when_a_later_signal_has_none():
    repo = FakeCompanyRepository(
        signals=[
            _signal("acme.com", "Acme", company_status="Active"),
            _signal("acme.com", "Acme", company_status=None),
        ]
    )
    writer = CompanyWriter(repo)

    written = writer.write_all()

    assert written == 1
    assert repo.upserted == [
        ("acme.com", {"name": "Acme", "company_status": "Active"}, False)
    ]


def test_write_all_keeps_a_known_scale_when_a_later_signal_has_no_headcount():
    repo = FakeCompanyRepository(
        signals=[
            _signal("acme.com", "Acme", team_size=7000),
            _signal("acme.com", "Acme", team_size=None),
        ]
    )
    writer = CompanyWriter(repo)

    written = writer.write_all()

    assert written == 1
    assert repo.upserted == [
        ("acme.com", {"name": "Acme", "company_scale": "1001+"}, False)
    ]


def test_write_all_carries_a_note_prefixed_with_yc_from_the_batch():
    repo = FakeCompanyRepository(
        signals=[_signal("acme.com", "Acme", batch="Summer 2023")]
    )
    writer = CompanyWriter(repo)

    writer.write_all()

    assert repo.upserted == [
        ("acme.com", {"name": "Acme", "notes": "YC Summer 2023"}, False)
    ]


def test_write_all_keeps_a_known_note_when_a_later_signal_has_none():
    """The HN case, and the reason this is a last-non-null merge: an HN
    signal read after a YC one carries no batch, and a plain last-row-wins
    collapse would erase it.
    """
    repo = FakeCompanyRepository(
        signals=[
            _signal("acme.com", "Acme", batch="Summer 2023"),
            _signal("acme.com", "Acme", batch=None),
        ]
    )
    writer = CompanyWriter(repo)

    written = writer.write_all()

    assert written == 1
    assert repo.upserted == [
        ("acme.com", {"name": "Acme", "notes": "YC Summer 2023"}, False)
    ]


def test_write_all_writes_no_note_at_all_when_the_batch_is_absent():
    """A blank note would be indistinguishable from a real one to a reader,
    and would overwrite a known note on a last-non-null merge.
    """
    repo = FakeCompanyRepository(signals=[_signal("acme.com", "Acme", batch=None)])

    CompanyWriter(repo).write_all()

    assert repo.upserted == [("acme.com", {"name": "Acme"}, False)]


def test_write_all_omits_notes_entirely_when_no_signal_carries_one():
    """Omitted rather than written as NULL, so gold.company keeps whatever an
    earlier run stored instead of being reset.
    """
    repo = FakeCompanyRepository(
        signals=[_signal("acme.com", "Acme", company_status="Active")]
    )
    writer = CompanyWriter(repo)

    writer.write_all()

    assert repo.upserted == [
        ("acme.com", {"name": "Acme", "company_status": "Active"}, False)
    ]


def test_notes_alone_write_no_history_row():
    """Type 1, like every field but the three in TYPE_2_TRACKED_FIELDS. A
    note is descriptive rather than a measured attribute, so there is nothing
    for a history row to record when it changes.
    """
    repo = FakeCompanyRepository(
        signals=[],
        companies={
            "acme.com": {
                "id": "c1",
                "business_sector": ["fintech"],
                "current_since": datetime(2026, 1, 1, tzinfo=UTC),
            }
        },
    )

    write_company(repo, "acme.com", {"name": "Acme", "notes": "YC S23"})

    assert repo.history_inserted == []
    assert repo.upserted[0][2] is False


def test_every_column_the_writer_sets_survives_the_repository_allowlist():
    """`build_upsert_query` drops any key not in `_COMPANY_COLUMNS`, so a
    writer key missing from that allowlist is written nowhere and silently
    discarded. The FakeCompanyRepository above records `new_values` without
    ever building SQL, so it cannot catch that on its own; this runs the
    writer for real and then feeds its output through the real query builder.
    """
    repo = FakeCompanyRepository(
        signals=[
            _signal(
                "acme.com",
                "Acme",
                stage="Growth",
                company_status="Active",
                team_size=700,
                industries=["B2B", "Fintech"],
                all_locations="Berlin, Germany",
                batch="Winter 2022",
            )
        ]
    )
    CompanyWriter(repo).write_all()

    _, new_values, _ = repo.upserted[0]
    sql, params = build_upsert_query("acme.com", new_values, bump_current_since=False)

    # Every key the writer produced survives the allowlist and appears as a
    # real column in the INSERT, rather than being silently filtered out.
    insert_columns = set(
        sql.split("(", 1)[1].split(")", 1)[0].replace(" ", "").split(",")
    )
    assert set(new_values) <= insert_columns
    assert len(params) == len(new_values) + 1  # +1 for the leading domain param
    assert set(new_values) <= set(_COMPANY_COLUMNS)


def test_write_all_opens_the_repository_scope_once_for_the_whole_batch():
    repo = FakeCompanyRepository(
        signals=[_signal("acme.com", "Acme"), _signal("getnao.io", "Nao")]
    )
    writer = CompanyWriter(repo)

    writer.write_all()

    assert repo.enter_count == 1
    assert repo.exit_count == 1


# Every case below is a shape observed in bronze.api_ingest, not invented.
# The counts in the docstrings are from the 6,252 live YC rows.


def test_parse_all_locations_reads_a_single_us_location():
    assert parse_all_locations("San Francisco, CA, USA") == ("San Francisco", "USA")


def test_parse_all_locations_takes_the_first_of_several_locations():
    """Multi-location is the common case: 1,088 of 6,252 rows are not a
    single 'City, Region, Country' entry. First entry is the primary one.
    """
    assert parse_all_locations("San Francisco, CA, USA; Mountain View, CA, USA") == (
        "San Francisco",
        "USA",
    )


def test_parse_all_locations_ignores_a_trailing_remote_marker():
    assert parse_all_locations("New York City, NY, USA; New York, NY, USA; Remote") == (
        "New York City",
        "USA",
    )


def test_parse_all_locations_reads_a_country_only_location():
    """'Singapore, Singapore' has no city segment of its own, so city is left
    None rather than repeating the country name. 203 live rows look like this.
    """
    assert parse_all_locations("Singapore, Singapore") == (None, "Singapore")


def test_parse_all_locations_reads_a_non_us_country():
    assert parse_all_locations("London, England, United Kingdom") == (
        "London",
        "United Kingdom",
    )


def test_parse_all_locations_returns_nothing_for_a_bare_remote():
    """44 live rows are literally 'Remote'. Recording that as a country
    would be worse than recording nothing.
    """
    assert parse_all_locations("Remote") == (None, None)


def test_parse_all_locations_returns_nothing_for_an_empty_string():
    """154 live rows have an empty all_locations."""
    assert parse_all_locations("") == (None, None)
    assert parse_all_locations("   ") == (None, None)


def test_parse_all_locations_returns_nothing_for_none():
    assert parse_all_locations(None) == (None, None)


def test_write_all_carries_business_sector_as_a_list():
    repo = FakeCompanyRepository(
        signals=[
            _signal("acme.com", "Acme", industries=["B2B", "Fintech"]),
        ]
    )

    CompanyWriter(repo).write_all()

    assert repo.upserted == [
        ("acme.com", {"name": "Acme", "business_sector": ["B2B", "Fintech"]}, False)
    ]


def test_write_all_keeps_a_known_sector_when_a_later_signal_has_none():
    """An HN signal carries no industries at all, so last-row-wins would
    wipe a YC company's sector on every mixed-source run.
    """
    repo = FakeCompanyRepository(
        signals=[
            _signal("acme.com", "Acme", industries=["Fintech"]),
            _signal("acme.com", "Acme", industries=None),
        ]
    )

    CompanyWriter(repo).write_all()

    assert repo.upserted == [
        ("acme.com", {"name": "Acme", "business_sector": ["Fintech"]}, False)
    ]


def test_write_all_keeps_a_known_sector_when_an_earlier_signal_had_none():
    repo = FakeCompanyRepository(
        signals=[
            _signal("acme.com", "Acme", industries=None),
            _signal("acme.com", "Acme", industries=["HealthCare"]),
        ]
    )

    CompanyWriter(repo).write_all()

    assert repo.upserted == [
        ("acme.com", {"name": "Acme", "business_sector": ["HealthCare"]}, False)
    ]


def test_write_all_prefers_the_latest_known_sector():
    repo = FakeCompanyRepository(
        signals=[
            _signal("acme.com", "Acme", industries=["Fintech"]),
            _signal("acme.com", "Acme", industries=["B2B", "Fintech"]),
        ]
    )

    CompanyWriter(repo).write_all()

    assert repo.upserted == [
        ("acme.com", {"name": "Acme", "business_sector": ["B2B", "Fintech"]}, False)
    ]


def test_write_all_parses_country_and_city_out_of_all_locations():
    repo = FakeCompanyRepository(
        signals=[_signal("acme.com", "Acme", all_locations="San Francisco, CA, USA")]
    )

    CompanyWriter(repo).write_all()

    assert repo.upserted == [
        (
            "acme.com",
            {
                "name": "Acme",
                "country": "USA",
                "city": "San Francisco",
            },
            False,
        )
    ]


def test_write_all_keeps_a_known_country_when_a_later_signal_has_no_location():
    repo = FakeCompanyRepository(
        signals=[
            _signal("acme.com", "Acme", all_locations="Berlin, Germany"),
            _signal("acme.com", "Acme", all_locations="Remote"),
        ]
    )

    CompanyWriter(repo).write_all()

    assert repo.upserted == [
        ("acme.com", {"name": "Acme", "country": "Germany", "city": "Berlin"}, False)
    ]


def test_write_all_omits_country_and_city_when_the_location_has_no_geography():
    """Nothing is written rather than writing a null, so a Gold run that
    only sees a bare 'Remote' leaves an earlier country alone.
    """
    repo = FakeCompanyRepository(
        signals=[_signal("acme.com", "Acme", all_locations="Remote")]
    )

    CompanyWriter(repo).write_all()

    assert repo.upserted == [("acme.com", {"name": "Acme"}, False)]
