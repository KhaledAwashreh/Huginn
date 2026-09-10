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
