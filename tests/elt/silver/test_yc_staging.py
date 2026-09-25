from __future__ import annotations

from datetime import UTC, datetime

from huginn.elt.silver.yc_staging import YcStagingLoader, parse_yc_listing

# Real YC Algolia hit shape (queried live, docs/sources/yc-directory.md).
_REAL_HIT_HIRING = {
    "id": 30405,
    "name": "nao Labs",
    "slug": "nao-labs",
    "batch": "Spring 2025",
    "stage": "Early",
    "website": "https://getnao.io/",
    "isHiring": True,
    "one_liner": "Open Source Analytics Agent",
    "long_description": "nao is an open source framework to build and deploy analytics agent.",
    "launched_at": 1744958361,
}

_REAL_HIT_NOT_HIRING = {
    "id": 595,
    "name": "Flexport",
    "slug": "flexport",
    "batch": "Winter 2014",
    "stage": "Growth",
    "website": "https://www.flexport.com/careers/jobs/",
    "isHiring": False,
    "one_liner": "Platform for global logistics.",
    "long_description": "Founded in 2013, we believe trade can move the human race forward.",
    "launched_at": 1384978752,
}

# Real shape: long_description null (confirmed live, 29/6204 rows).
_REAL_HIT_NULL_LONG_DESCRIPTION = {
    "id": 1,
    "name": "NullDescCo",
    "slug": "nulldescco",
    "batch": "Winter 2020",
    "stage": "Early",
    "website": "https://nulldescco.example",
    "isHiring": True,
    "one_liner": "The one-liner fallback.",
    "long_description": None,
    "launched_at": 1600000000,
}


# Real shape: registry lifecycle and headcount both present. Values are a real
# active listing with a mid-size team, so the assertions below are about
# pass-through rather than about any interpretation of the numbers.
_REAL_HIT_WITH_STATUS_AND_HEADCOUNT = {
    **_REAL_HIT_HIRING,
    "status": "Active",
    "team_size": 50,
}

# Real shape: 133 live rows report 0 rather than omitting the key. It reads as
# pre-first-hire (41 of them are Active, all have a batch and industry), so
# the parser must not collapse a reported 0 into the absent case: the
# distinction is what lets Gold put it in the lowest band deliberately.
_REAL_HIT_ZERO_HEADCOUNT = {
    **_REAL_HIT_HIRING,
    "id": 777,
    "slug": "prehire-co",
    "status": "Active",
    "team_size": 0,
}


def test_parse_yc_listing_company_name_is_the_name_field():
    result = parse_yc_listing(_REAL_HIT_HIRING)

    assert result.company_name_raw == "nao Labs"


def test_parse_yc_listing_website_is_the_website_field():
    result = parse_yc_listing(_REAL_HIT_HIRING)

    assert result.website == "https://getnao.io/"


def test_parse_yc_listing_signal_type_is_hiring_when_is_hiring_true():
    result = parse_yc_listing(_REAL_HIT_HIRING)

    assert result.signal_type == "hiring"


def test_parse_yc_listing_signal_type_is_program_milestone_when_not_hiring():
    result = parse_yc_listing(_REAL_HIT_NOT_HIRING)

    assert result.signal_type == "program_milestone"


def test_parse_yc_listing_stage_passes_through_unmapped():
    assert parse_yc_listing(_REAL_HIT_HIRING).stage == "Early"
    assert parse_yc_listing(_REAL_HIT_NOT_HIRING).stage == "Growth"


def test_parse_yc_listing_company_status_passes_through_unmapped():
    """Free text, not an enum: the source's spelling survives untouched."""
    assert (
        parse_yc_listing(_REAL_HIT_WITH_STATUS_AND_HEADCOUNT).company_status == "Active"
    )


def test_parse_yc_listing_company_status_is_none_when_the_key_is_absent():
    assert parse_yc_listing(_REAL_HIT_HIRING).company_status is None


def test_parse_yc_listing_team_size_is_the_reported_headcount():
    """The raw integer, not a band. Bucketing into company_scale bands is
    Gold's job (see gold.company.team_size_to_scale): the bands are Huginn's
    vocabulary, and Silver conforms a source rather than re-expressing it.
    """
    assert parse_yc_listing(_REAL_HIT_WITH_STATUS_AND_HEADCOUNT).team_size == 50


def test_parse_yc_listing_team_size_zero_is_kept_rather_than_treated_as_absent():
    """A reported 0 is a real value, not a missing one."""
    assert parse_yc_listing(_REAL_HIT_ZERO_HEADCOUNT).team_size == 0


def test_parse_yc_listing_team_size_is_none_when_the_key_is_absent():
    assert parse_yc_listing(_REAL_HIT_HIRING).team_size is None


def test_parse_yc_listing_industries_keeps_every_value_in_source_order():
    """A list on 78% of live rows, so collapsing it to one value would
    discard most of what the source said. Order preserved because
    `industry` is always `industries[0]`, making the first element primary.
    """
    hit = {**_REAL_HIT_HIRING, "industries": ["B2B", "Fintech", "HealthCare"]}

    assert parse_yc_listing(hit).industries == ("B2B", "Fintech", "HealthCare")


def test_parse_yc_listing_industries_is_none_when_the_key_is_absent():
    """None, not an empty tuple: 'this source does not report industries'
    and 'reports no industries' must stay distinguishable, because Gold
    treats a null as absent and an empty array as a real value.
    """
    assert parse_yc_listing(_REAL_HIT_HIRING).industries is None


def test_parse_yc_listing_industries_is_an_empty_tuple_for_an_empty_array():
    """The other half of the None-versus-empty distinction: a key present
    with an empty list is the source reporting no industries, which is a
    real value, so it must not collapse into None.
    """
    hit = {**_REAL_HIT_HIRING, "industries": []}

    assert parse_yc_listing(hit).industries == ()


def test_parse_yc_listing_former_names_keeps_every_value_in_source_order():
    """Captured verbatim for the KAN-4 matcher, uncleaned: case variants of
    the current name and self-referential entries are all kept as sent, so
    whoever builds the matcher decides how to treat them against real data.
    """
    hit = {**_REAL_HIT_HIRING, "former_names": ["ZenPayroll", "Zen Payroll"]}

    assert parse_yc_listing(hit).former_names == ("ZenPayroll", "Zen Payroll")


def test_parse_yc_listing_former_names_is_none_when_the_key_is_absent():
    assert parse_yc_listing(_REAL_HIT_HIRING).former_names is None


def test_parse_yc_listing_former_names_is_an_empty_tuple_for_an_empty_array():
    """Present on 3,054 of 6,252 live rows, so absent is the common case;
    an explicitly empty array is still a value rather than an absence.
    """
    hit = {**_REAL_HIT_HIRING, "former_names": []}

    assert parse_yc_listing(hit).former_names == ()


def test_parse_yc_listing_all_locations_is_the_display_string_verbatim():
    """Kept unparsed. Splitting it is Gold's interpretation to own, the same
    split that keeps team_size raw in Silver and bands it in Gold.
    """
    hit = {**_REAL_HIT_HIRING, "all_locations": "San Francisco, CA, USA; Remote"}

    assert parse_yc_listing(hit).all_locations == "San Francisco, CA, USA; Remote"


def test_parse_yc_listing_all_locations_is_none_when_the_key_is_absent():
    assert parse_yc_listing(_REAL_HIT_HIRING).all_locations is None


def test_parse_yc_listing_batch_is_the_source_label_verbatim():
    """The batch is when YC funded the company, which is the date Huginn
    actually wants for 'joined the portal'. It is NOT `launched_at`, which is
    a different and largely independent event: verified live, the 90-company
    'Fall 2026' batch spans 19 months of distinct launched_at values, and
    every batch from Summer 2005 to Winter 2011 has its earliest launched_at
    on 2012-01-17, a profile backfill wave. So the label is kept as its own
    column rather than inferred from the timestamp.
    """
    hit = {**_REAL_HIT_HIRING, "batch": "Winter 2022"}

    assert parse_yc_listing(hit).batch == "Winter 2022"


def test_parse_yc_listing_batch_is_none_when_the_key_is_absent():
    hit = {k: v for k, v in _REAL_HIT_HIRING.items() if k != "batch"}

    assert parse_yc_listing(hit).batch is None


def test_parse_yc_listing_keeps_an_unspecified_batch_verbatim():
    """YC's literal 'Unspecified' means "this company has no batch", which
    is a value the source does supply, not a missing field. Collapsing it to
    NULL would lose the difference between YC saying so and the key being
    absent; exactly one live row carries it.
    """
    hit = {**_REAL_HIT_HIRING, "batch": "Unspecified"}

    assert parse_yc_listing(hit).batch == "Unspecified"


def test_parse_yc_listing_description_prefers_long_description():
    result = parse_yc_listing(_REAL_HIT_HIRING)

    assert result.description == (
        "nao is an open source framework to build and deploy analytics agent."
    )


def test_parse_yc_listing_description_falls_back_to_one_liner_when_null():
    result = parse_yc_listing(_REAL_HIT_NULL_LONG_DESCRIPTION)

    assert result.description == "The one-liner fallback."


def test_parse_yc_listing_stable_id_is_the_id_as_a_string():
    result = parse_yc_listing(_REAL_HIT_HIRING)

    assert result.stable_id == "30405"


def test_parse_yc_listing_url_is_the_directory_profile_url():
    result = parse_yc_listing(_REAL_HIT_HIRING)

    assert result.url == "https://www.ycombinator.com/companies/nao-labs"


def test_parse_yc_listing_occurred_on_is_launched_at_as_utc():
    result = parse_yc_listing(_REAL_HIT_HIRING)

    assert result.occurred_on == datetime.fromtimestamp(1744958361, tz=UTC)


def test_yc_listing_staging_is_frozen():
    result = parse_yc_listing(_REAL_HIT_HIRING)

    try:
        result.company_name_raw = "changed"
        raise AssertionError("expected FrozenInstanceError")
    except AttributeError:
        pass


class FakeYcStagingRepository:
    def __init__(self, payloads: list[dict]) -> None:
        self._payloads = payloads
        self.read_calls: list[str] = []
        self.upserted = []
        self.enter_count = 0
        self.exit_count = 0

    def __enter__(self):
        self.enter_count += 1
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.exit_count += 1

    def read(self, source: str) -> list[dict]:
        self.read_calls.append(source)
        return self._payloads

    def upsert(self, row) -> None:
        self.upserted.append(row)


def test_load_upserts_every_row():
    repository = FakeYcStagingRepository([_REAL_HIT_HIRING, _REAL_HIT_NOT_HIRING])
    loader = YcStagingLoader(repository)

    loader.load()

    assert {row.stable_id for row in repository.upserted} == {"30405", "595"}


def test_load_returns_the_count_of_rows_written():
    repository = FakeYcStagingRepository([_REAL_HIT_HIRING, _REAL_HIT_NOT_HIRING])
    loader = YcStagingLoader(repository)

    written = loader.load()

    assert written == 2


def test_load_reads_the_yc_source():
    repository = FakeYcStagingRepository([_REAL_HIT_HIRING])
    loader = YcStagingLoader(repository)

    loader.load()

    assert repository.read_calls == ["yc"]


def test_load_opens_the_repository_scope_once_for_the_whole_batch():
    """Regression check: the batch must share one connection scope rather
    than opening one per record."""
    repository = FakeYcStagingRepository([_REAL_HIT_HIRING, _REAL_HIT_NOT_HIRING])
    loader = YcStagingLoader(repository)

    loader.load()

    assert repository.enter_count == 1
    assert repository.exit_count == 1


# A company that is acquired or shut down is not a prospect, so it never
# reaches silver at all. Statuses below are YC's own vocabulary, confirmed on
# all 6,252 live rows: Active 4,326 / Inactive 1,080 / Acquired 823 / Public 23.


def test_parse_yc_listing_returns_none_for_an_acquired_company():
    hit = {**_REAL_HIT_HIRING, "status": "Acquired"}

    assert parse_yc_listing(hit) is None


def test_parse_yc_listing_returns_none_for_an_inactive_company():
    hit = {**_REAL_HIT_HIRING, "status": "Inactive"}

    assert parse_yc_listing(hit) is None


def test_parse_yc_listing_keeps_a_public_company():
    """Public is the opposite of dead. A listed company is not a prospect
    either, but excluding it here would mean the rule is "not Active" rather
    than the narrower "no longer operating under its own name".
    """
    assert parse_yc_listing({**_REAL_HIT_HIRING, "status": "Public"}) is not None


def test_parse_yc_listing_keeps_an_active_company():
    assert parse_yc_listing({**_REAL_HIT_HIRING, "status": "Active"}) is not None


def test_parse_yc_listing_keeps_a_company_with_no_status():
    """An absent status means this source did not say, which is not the same
    claim as "acquired". Dropping it would quietly discard a company on a
    missing field rather than on a stated one.
    """
    hit = {k: v for k, v in _REAL_HIT_HIRING.items() if k != "status"}

    assert parse_yc_listing(hit) is not None


def test_load_skips_excluded_companies_and_counts_only_kept_rows():
    repository = FakeYcStagingRepository(
        payloads=[
            {**_REAL_HIT_HIRING, "id": 1, "status": "Active"},
            {**_REAL_HIT_HIRING, "id": 2, "status": "Acquired"},
            {**_REAL_HIT_HIRING, "id": 3, "status": "Inactive"},
            {**_REAL_HIT_HIRING, "id": 4, "status": "Public"},
        ]
    )

    written = YcStagingLoader(repository).load()

    assert written == 2
    assert [row.stable_id for row in repository.upserted] == ["1", "4"]
