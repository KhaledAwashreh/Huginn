from __future__ import annotations

import logging
from datetime import UTC, datetime

from huginn.elt.silver import yc_staging
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


def test_parse_yc_listing_description_is_null_when_neither_key_is_present():
    """A hit carrying no tagline at all is still a usable listing.

    `one_liner` and `long_description` are present on all 6,252 bronze rows
    as of 2026-09, but `description` is a display string, not an identity
    field, so an absent one must not raise. NULL rather than "" because the
    column is nullable and this repo keeps "the source did not report it"
    distinct from "the source reported it as nothing", the same distinction
    `_as_str_tuple` preserves for the list columns.
    """
    hit = {
        k: v
        for k, v in _REAL_HIT_HIRING.items()
        if k not in ("one_liner", "long_description")
    }

    assert parse_yc_listing(hit).description is None


def test_parse_yc_listing_falls_back_when_the_long_description_is_empty():
    """The shape that occurs most in live data, and the one that broke.

    386 live YC rows carry an empty `long_description` and 344 of those have
    a populated `one_liner`. Treating "" as a present value therefore blanks
    the description on 210 currently staged rows. An empty string has to fall
    through to the fallback, which is what the `or` is for.
    """
    result = parse_yc_listing(
        {**_REAL_HIT_HIRING, "long_description": "", "one_liner": "A B2B tool."}
    )

    assert result.description == "A B2B tool."


def test_parse_yc_listing_keeps_a_present_but_empty_description_as_empty():
    """Both keys present and both empty: "" is what the source actually sent.

    Distinct from absent, and distinct from the fallback case above, where
    one key was empty and the other was not.
    """
    hit = {
        **_REAL_HIT_HIRING,
        "long_description": "",
        "one_liner": "",
    }

    assert parse_yc_listing(hit).description == ""


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


# `launched_at` is non-null on all 6,252 bronze rows as of 2026-09, so unlike
# the fields above it is not a shape the live directory currently shows. It is
# still the only optional field whose absence makes a row unpromotable rather
# than merely thinner, because `occurred_on` is the signal's own date and every
# Silver table holds it nullable but no layer invents a substitute. `id`,
# `name`, and `slug` are unpromotable when absent too, but through the rejected
# bucket rather than a skip reason, since there is no stable key without them.


def test_parse_yc_listing_does_not_promote_a_listing_with_no_launch_date():
    assert parse_yc_listing({**_REAL_HIT_HIRING, "launched_at": None}) is None


def test_parse_yc_listing_does_not_promote_a_listing_with_no_launch_date_key():
    hit = {k: v for k, v in _REAL_HIT_HIRING.items() if k != "launched_at"}

    assert parse_yc_listing(hit) is None


def test_load_names_an_undated_listing_in_a_warning(caplog):
    """A dropped listing has to name itself, or it is invisible.

    Asserted through `load`, not through `parse_yc_listing`, because that is
    the only path that reports: `load` consults `_skip_reason` before calling
    the parser, so a warning inside the parser would never fire in the
    pipeline. The bucket count is only visible at INFO, so this is what makes
    the reason traceable to a specific YC id.
    """
    repository = FakeYcStagingRepository(
        payloads=[{**_REAL_HIT_HIRING, "id": 30405, "launched_at": None}]
    )

    with caplog.at_level(logging.WARNING, logger="huginn.elt.silver.yc_staging"):
        YcStagingLoader(repository).load()

    warnings = [
        record
        for record in caplog.records
        if "not promoting listing" in record.getMessage()
    ]
    assert len(warnings) == 1
    assert warnings[0].levelno == logging.WARNING
    assert "30405" in warnings[0].getMessage()
    assert "launched_at" in warnings[0].getMessage()


def test_load_writes_the_usable_rows_when_one_listing_has_no_launch_date():
    """One unusable hit must not cost the whole batch.

    An undated hit never raises: `parse_yc_listing` returns None for it and
    the loop continues to the next payload. This is the case that motivated
    splitting the skip buckets, because a missing launch date is a data
    problem and reporting it as "not a prospect" would hide it.
    """
    repository = FakeYcStagingRepository(
        payloads=[
            {**_REAL_HIT_HIRING, "id": 1},
            {**_REAL_HIT_HIRING, "id": 2, "launched_at": None},
            {**_REAL_HIT_HIRING, "id": 3},
        ]
    )

    written = YcStagingLoader(repository).load()

    assert written == 2
    assert [row.stable_id for row in repository.upserted] == ["1", "3"]


# A payload can still be malformed in a way the parser does not anticipate.
# The two guards above remove the known triggers; this is the net for anything
# else, so one odd hit cannot wedge the table on every future run. Bronze is
# immutable and the loader re-reads it whole, so an escaping error is not a
# lost run, it is a permanent outage (Jira KAN-34).


def test_load_survives_a_listing_missing_its_name():
    """`id`, `name`, and `slug` are the three fields the docstring treats as
    always present, and they are still indexed directly. If YC ever omits
    one, that row is dropped and named, not fatal.
    """
    hit = {k: v for k, v in _REAL_HIT_HIRING.items() if k != "name"}
    repository = FakeYcStagingRepository(payloads=[hit, {**_REAL_HIT_HIRING, "id": 2}])

    written = YcStagingLoader(repository).load()

    assert written == 1
    assert [row.stable_id for row in repository.upserted] == ["2"]


def test_load_survives_a_listing_whose_launch_date_is_a_string():
    """A string where a timestamp belongs.

    Note the distinction from the out-of-range case below: a non-numeric
    *type* is a TypeError, which the narrow catch has always covered. This is
    the case the live data has never shown, pinned because the guard is what
    keeps it from becoming an outage.
    """
    repository = FakeYcStagingRepository(
        payloads=[
            {**_REAL_HIT_HIRING, "id": 1, "launched_at": "not-a-timestamp"},
            {**_REAL_HIT_HIRING, "id": 2},
        ]
    )

    written = YcStagingLoader(repository).load()

    assert written == 1
    assert [row.stable_id for row in repository.upserted] == ["2"]


def test_load_survives_a_launch_date_out_of_range_for_the_platform():
    """The case that made the catch wrong once already.

    `datetime.fromtimestamp` does not report an out-of-range timestamp the
    same way every time. A value past the platform's `time_t` raises
    `OverflowError`, and a value past what the C library will accept raises
    `OSError` with errno 75. Neither is a `ValueError` subclass, so a tuple
    naming only OverflowError let `OSError` escape into the shared
    transaction and roll back the whole batch, which is the outage this
    loader is meant to prevent. Both are verified here rather than assumed,
    because which one you get depends on the platform and the magnitude.
    """
    for out_of_range in (10**20, 1e18):
        repository = FakeYcStagingRepository(
            payloads=[
                {**_REAL_HIT_HIRING, "id": 1, "launched_at": out_of_range},
                {**_REAL_HIT_HIRING, "id": 2},
            ]
        )

        written = YcStagingLoader(repository).load()

        assert written == 1, f"{out_of_range!r} escaped and rolled the batch back"
        assert [row.stable_id for row in repository.upserted] == ["2"]


def test_load_survives_a_launch_date_the_calendar_cannot_represent():
    """The nearest out-of-range band, and the one most likely in practice.

    `fromtimestamp` reports this as ValueError ("year must be in 1..9999"),
    which is a different exception from the two far-out bands covered above.
    Without ValueError in the catch, a plausible-looking but wrong
    millisecond-scale timestamp would roll back the batch.
    """
    repository = FakeYcStagingRepository(
        payloads=[
            {**_REAL_HIT_HIRING, "id": 1, "launched_at": 1e12},
            {**_REAL_HIT_HIRING, "id": 2},
        ]
    )

    written = YcStagingLoader(repository).load()

    assert written == 1
    assert [row.stable_id for row in repository.upserted] == ["2"]


def test_load_survives_a_listing_whose_industries_is_not_a_list():
    """`_as_str_tuple` calls `tuple(value)`, so a scalar where a list belongs
    raises. `None` is already handled as absent; a wrong type is not.
    """
    repository = FakeYcStagingRepository(
        payloads=[
            {**_REAL_HIT_HIRING, "id": 1, "industries": 7},
            {**_REAL_HIT_HIRING, "id": 2},
        ]
    )

    written = YcStagingLoader(repository).load()

    assert written == 1
    assert [row.stable_id for row in repository.upserted] == ["2"]


def test_load_reports_an_unusable_listing_in_the_summary(caplog):
    """A skipped row must be countable, or "we dropped it" is invisible.

    Five counts, deliberately distinct: written, not a prospect, absent or
    null launch date, unnamed reason, and unparseable. The middle three are
    all "not promoted" but are not the same event, and folding them together
    would let a source-side data problem look like a deliberate business-rule
    exclusion. The counts must also account for every bronze row, which is
    what makes a row lost to a missing bucket visible.
    """
    repository = FakeYcStagingRepository(
        payloads=[
            {**_REAL_HIT_HIRING, "id": 1, "status": "Active"},
            {**_REAL_HIT_HIRING, "id": 2, "status": "Acquired"},
            {**_REAL_HIT_HIRING, "id": 3, "status": "Inactive"},
            {**_REAL_HIT_HIRING, "id": 4, "launched_at": None},
            {**_REAL_HIT_HIRING, "id": 5, "industries": 7},
        ]
    )

    with caplog.at_level(logging.INFO, logger="huginn.elt.silver.yc_staging"):
        written = YcStagingLoader(repository).load()

    assert written == 1
    assert "1 written" in caplog.text
    assert "2 skipped as not a prospect" in caplog.text
    assert "1 skipped for an absent or null launched_at" in caplog.text
    assert "0 skipped for an unclassified reason" in caplog.text
    assert "1 rejected as unparseable" in caplog.text
    # 1 written + 2 not-a-prospect + 1 undated + 1 rejected == 5 bronze rows.
    assert "of 5 bronze rows" in caplog.text


def test_a_hit_that_is_both_excluded_and_undated_is_counted_once_as_excluded(
    caplog,
):
    """`_skip_reason` is status-first, and the precedence is now pinned.

    An acquired company that is also undated is one row with two reasons. It
    is counted as not a prospect and not additionally as undated, so the
    counts still sum to the bronze row count. The cost is that its missing
    date goes unreported, which is acceptable only because `launched_at` is
    non-null on every live YC row today.
    """
    repository = FakeYcStagingRepository(
        payloads=[
            {
                **_REAL_HIT_HIRING,
                "id": 1,
                "status": "Acquired",
                "launched_at": None,
            },
        ]
    )

    with caplog.at_level(logging.INFO, logger="huginn.elt.silver.yc_staging"):
        written = YcStagingLoader(repository).load()

    assert written == 0
    assert "1 skipped as not a prospect" in caplog.text
    assert "0 skipped for an absent or null launched_at" in caplog.text
    assert "0 rejected as unparseable" in caplog.text
    assert "of 1 bronze rows" in caplog.text


def test_an_upsert_failure_is_not_mistaken_for_bad_source_data():
    """`upsert` sits outside the parse catch, and has to stay there.

    A SQL error inside a Postgres transaction aborts it, so catching one
    would report a row as rejected while the batch was already doomed. This
    test fails if anyone moves the write inside the `try`.
    """
    repository = FakeYcStagingRepository(
        payloads=[{**_REAL_HIT_HIRING, "id": 1}],
    )

    def explode(_row: object) -> None:
        raise KeyError("simulated database failure")

    repository.upsert = explode

    try:
        YcStagingLoader(repository).load()
        raise AssertionError("expected the upsert failure to propagate")
    except KeyError:
        pass


def test_rejecting_a_row_does_not_open_a_second_transaction():
    """All-or-nothing, checked with a rejection actually in the batch.

    The pre-existing scope test above covers the plain two-row case; this one
    adds the input that could plausibly tempt a per-row scope, namely a row
    being skipped. A rejected row must not get a transaction of its own, and
    the rows around it must still be written into the one shared scope.
    """
    repository = FakeYcStagingRepository(
        payloads=[
            {**_REAL_HIT_HIRING, "id": 1, "industries": 7},
            {**_REAL_HIT_HIRING, "id": 2},
        ]
    )

    YcStagingLoader(repository).load()

    assert repository.enter_count == 1
    assert repository.exit_count == 1
    assert [row.stable_id for row in repository.upserted] == ["2"]


def test_load_does_not_swallow_an_unexpected_error():
    """The net is deliberately narrow, per BEST_PRACTICES.md:197-200: a
    defect of an unexpected class (here a non-mapping payload reaching the
    parser, which raises AttributeError) must still surface rather than be
    reclassified as bad source data.
    """
    repository = FakeYcStagingRepository(
        payloads=[{**_REAL_HIT_HIRING, "id": 1}],
    )
    repository.read = lambda source: [None]

    try:
        YcStagingLoader(repository).load()
        raise AssertionError("expected AttributeError to propagate")
    except AttributeError:
        pass


def test_load_logs_the_rejected_listing_with_its_id_and_error(caplog):
    """ADR-0005: log at the stage boundary, with enough to find the row.

    Bronze is the as-fetched record, so the id named here is the only handle
    back to the offending payload. The level is pinned too, not just the
    text: this is a per-row WARNING, and promoting it to ERROR would make a
    single bad row look like a stage failure.
    """
    repository = FakeYcStagingRepository(
        payloads=[{**_REAL_HIT_HIRING, "id": 4242, "industries": 7}]
    )

    with caplog.at_level(logging.WARNING, logger="huginn.elt.silver.yc_staging"):
        YcStagingLoader(repository).load()

    rejected = [
        record
        for record in caplog.records
        if "rejected unparseable listing" in record.getMessage()
    ]
    assert len(rejected) == 1
    assert rejected[0].levelno == logging.WARNING
    assert "4242" in rejected[0].getMessage()
    assert "TypeError" in rejected[0].getMessage()


def test_a_skip_reason_this_summary_does_not_name_is_warned_not_bucketed(
    monkeypatch, caplog
):
    """An unnamed skip reason must announce itself, not vanish.

    `_skip_reason` is the only place the skip conditions are written, and
    `load` buckets the reasons it knows by name. This covers the case where
    someone adds a reason there and forgets the summary: the row is not
    promoted either way, but it is counted separately and warned, so it
    cannot be mistaken for a deliberate business-rule exclusion.
    """
    monkeypatch.setattr(
        yc_staging, "_skip_reason", lambda payload: "a reason added later"
    )
    repository = FakeYcStagingRepository(
        payloads=[{**_REAL_HIT_HIRING, "id": 77}],
    )

    with caplog.at_level(logging.INFO, logger="huginn.elt.silver.yc_staging"):
        written = YcStagingLoader(repository).load()

    assert written == 0
    assert repository.upserted == []
    warned = [
        record
        for record in caplog.records
        if "skipped listing id=" in record.getMessage()
    ]
    assert len(warned) == 1
    assert "77" in warned[0].getMessage()
    assert "a reason added later" in warned[0].getMessage()
    assert "0 skipped as not a prospect" in caplog.text
    assert "1 skipped for an unclassified reason" in caplog.text


def test_an_excluded_company_is_counted_but_not_warned_about(caplog):
    """Pins the count-only choice for the not-a-prospect bucket.

    1,903 of 6,252 live rows are excluded this way, so a per-row warning for
    each would bury the summary and drown the buckets that do deserve
    attention. That is a deliberate trade, and `docs/entities.md` states it,
    so it is asserted here rather than left as a comment that can drift.
    """
    repository = FakeYcStagingRepository(
        payloads=[
            {**_REAL_HIT_HIRING, "id": 1, "status": "Acquired"},
            {**_REAL_HIT_HIRING, "id": 2, "status": "Inactive"},
            {**_REAL_HIT_HIRING, "id": 3, "status": "Acquired"},
        ]
    )

    with caplog.at_level(logging.INFO, logger="huginn.elt.silver.yc_staging"):
        YcStagingLoader(repository).load()

    at_warning_or_above = [
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.WARNING
    ]
    assert at_warning_or_above == []
    assert "3 skipped as not a prospect" in caplog.text
