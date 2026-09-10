from __future__ import annotations

from datetime import UTC, datetime

from huginn.elt.silver.hn_staging import HnStagingLoader, parse_hn_posting

# Real "Who's Hiring" comment, HTML-escaped exactly as Firebase returns it
# (confirmed live, architecture-notes/hn-fetch-plan.md).
_REAL_COMMENT_WITH_TRAILING_LINK = {
    "id": 49522903,
    "type": "comment",
    "parent": 49522897,
    "time": 1757404800,
    "by": "modash_hn",
    "text": (
        "Modash.io | Senior Product Engineer | Remote (Europe) | Full-time | "
        '&#x20;75k–110k | <a href="https:&#x2F;&#x2F;modash.io" rel="nofollow">'
        "https:&#x2F;&#x2F;modash.io</a><p>Modash helps brands find, manage, and "
        "pay creators."
    ),
}

# Real shape: link is merged into the company-name field itself, not a
# separate trailing field.
_REAL_COMMENT_WITH_INLINE_COMPANY_LINK = {
    "id": 49522999,
    "type": "comment",
    "parent": 49522897,
    "time": 1757404900,
    "by": "snout_hn",
    "text": (
        'Snout <a href="https:&#x2F;&#x2F;snout.com&#x2F;" rel="nofollow">'
        "https:&#x2F;&#x2F;snout.com&#x2F;</a> | Multiple Engineering + Product "
        "Roles | Remote US or Ontario, Canada | Full Time<p>Join us at Snout."
    ),
}

# Real shape: no <a href> anywhere (~11% of live postings, per
# docs/entities.md's Website nullability note).
_REAL_COMMENT_WITH_NO_LINK = {
    "id": 49523010,
    "type": "comment",
    "parent": 49522897,
    "time": 1757405000,
    "by": "origamics_hn",
    "text": (
        "ORIGAMICS | Founding Researcher | San Francisco | ONSITE&#x2F;REMOTE"
        "<p>Origamics is building AI models that reason about electronics."
    ),
}

# Real shape: no | at all (confirmed live meta-comment, not a posting).
_REAL_COMMENT_WITH_NO_PIPE = {
    "id": 49523099,
    "type": "comment",
    "parent": 49522897,
    "time": 1757405100,
    "by": "commenter_hn",
    "text": (
        "Please normalize <i>4DWW</i> - <i>Four Day Work Week</i><p>Whoever "
        "posts this monthly, please include the tag in your description."
    ),
}

# Real shape: | header present but no <p> at all (one-line posting).
_REAL_COMMENT_WITH_NO_PARAGRAPH_BREAK = {
    "id": 49523200,
    "type": "comment",
    "parent": 49522897,
    "time": 1757405200,
    "by": "shortpost_hn",
    "text": "Acme Corp | Backend Engineer | Remote | Full-time",
}

_REAL_ROOT_STORY = {
    "id": 49522897,
    "type": "story",
    "time": 1757404000,
    "by": "whoishiring",
    "title": "Ask HN: Who is hiring? (September 2026)",
    "kids": [49522903, 49522999],
}

_REAL_DELETED_COMMENT = {
    "id": 49522950,
    "type": "comment",
    "parent": 49522897,
    "deleted": True,
}


def test_parse_hn_posting_extracts_company_name_from_first_pipe_field():
    result = parse_hn_posting(_REAL_COMMENT_WITH_TRAILING_LINK)

    assert result.company_name_raw == "Modash.io"


def test_parse_hn_posting_extracts_website_from_trailing_link_field():
    result = parse_hn_posting(_REAL_COMMENT_WITH_TRAILING_LINK)

    assert result.website == "https://modash.io"


def test_parse_hn_posting_extracts_website_merged_into_company_field():
    result = parse_hn_posting(_REAL_COMMENT_WITH_INLINE_COMPANY_LINK)

    assert result.company_name_raw == "Snout"
    assert result.website == "https://snout.com/"


def test_parse_hn_posting_website_is_none_when_no_link_present():
    result = parse_hn_posting(_REAL_COMMENT_WITH_NO_LINK)

    assert result.website is None
    assert result.company_name_raw == "ORIGAMICS"


def test_parse_hn_posting_uses_whole_header_as_company_name_when_no_pipe():
    result = parse_hn_posting(_REAL_COMMENT_WITH_NO_PIPE)

    assert result.company_name_raw == "Please normalize 4DWW - Four Day Work Week"
    assert result.website is None


def test_parse_hn_posting_description_is_empty_when_no_paragraph_break():
    result = parse_hn_posting(_REAL_COMMENT_WITH_NO_PARAGRAPH_BREAK)

    assert result.company_name_raw == "Acme Corp"
    assert result.description == ""


def test_parse_hn_posting_description_is_cleaned_html():
    result = parse_hn_posting(_REAL_COMMENT_WITH_TRAILING_LINK)

    assert result.description == "Modash helps brands find, manage, and pay creators."


def test_parse_hn_posting_signal_type_is_always_hiring():
    result = parse_hn_posting(_REAL_COMMENT_WITH_TRAILING_LINK)

    assert result.signal_type == "hiring"


def test_parse_hn_posting_stage_is_always_none():
    result = parse_hn_posting(_REAL_COMMENT_WITH_TRAILING_LINK)

    assert result.stage is None


def test_parse_hn_posting_stable_id_is_the_item_id_as_a_string():
    result = parse_hn_posting(_REAL_COMMENT_WITH_TRAILING_LINK)

    assert result.stable_id == "49522903"


def test_parse_hn_posting_url_is_the_hn_permalink():
    result = parse_hn_posting(_REAL_COMMENT_WITH_TRAILING_LINK)

    assert result.url == "https://news.ycombinator.com/item?id=49522903"


def test_parse_hn_posting_occurred_on_is_the_item_time_as_utc():
    result = parse_hn_posting(_REAL_COMMENT_WITH_TRAILING_LINK)

    assert result.occurred_on == datetime.fromtimestamp(1757404800, tz=UTC)


def test_parse_hn_posting_returns_none_for_the_root_story():
    assert parse_hn_posting(_REAL_ROOT_STORY) is None


def test_parse_hn_posting_returns_none_for_a_deleted_comment():
    assert parse_hn_posting(_REAL_DELETED_COMMENT) is None


def test_hn_posting_staging_is_frozen():
    result = parse_hn_posting(_REAL_COMMENT_WITH_TRAILING_LINK)

    try:
        result.company_name_raw = "changed"
        raise AssertionError("expected FrozenInstanceError")
    except AttributeError:
        pass


class FakeHnStagingRepository:
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


def test_load_upserts_every_parseable_row_and_skips_unparseable_ones():
    repository = FakeHnStagingRepository(
        [
            _REAL_COMMENT_WITH_TRAILING_LINK,
            _REAL_ROOT_STORY,
            _REAL_DELETED_COMMENT,
            _REAL_COMMENT_WITH_NO_LINK,
        ]
    )
    loader = HnStagingLoader(repository)

    loader.load()

    assert {row.stable_id for row in repository.upserted} == {
        "49522903",
        "49523010",
    }


def test_load_returns_the_count_of_rows_upserted_not_read():
    repository = FakeHnStagingRepository(
        [
            _REAL_COMMENT_WITH_TRAILING_LINK,
            _REAL_ROOT_STORY,
            _REAL_DELETED_COMMENT,
            _REAL_COMMENT_WITH_NO_LINK,
        ]
    )
    loader = HnStagingLoader(repository)

    written = loader.load()

    assert written == 2


def test_load_reads_the_hn_source():
    repository = FakeHnStagingRepository([_REAL_COMMENT_WITH_TRAILING_LINK])
    loader = HnStagingLoader(repository)

    loader.load()

    assert repository.read_calls == ["hn"]


def test_load_opens_the_repository_scope_once_for_the_whole_batch():
    """Regression check: the batch must share one connection scope rather
    than opening one per record."""
    repository = FakeHnStagingRepository(
        [_REAL_COMMENT_WITH_TRAILING_LINK, _REAL_COMMENT_WITH_NO_LINK]
    )
    loader = HnStagingLoader(repository)

    loader.load()

    assert repository.enter_count == 1
    assert repository.exit_count == 1
