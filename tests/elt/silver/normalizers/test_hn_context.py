from huginn.elt.silver.normalizers.hn_context import normalize_hn


def test_preserves_complete_unicode_header_body_and_links():
    extraction = normalize_hn(
        {
            "id": 123,
            "type": "comment",
            "time": 1_700_000_000,
            "text": (
                'München Labs | Senior Engineer | Full-time | <a href="https://example.test">'
                "company site</a><p>Build café tools &amp; ship them.<p>Second paragraph"
                " <a href='https://jobs.example.test'>open roles</a>"
            ),
        }
    )

    assert extraction.source == "hn"
    assert extraction.stable_id == "123"
    assert extraction.status == "captured"
    assert extraction.source_url == "https://news.ycombinator.com/item?id=123"
    expected_text = (
        "München Labs | Senior Engineer | Full-time | company site\n"
        "Build café tools & ship them.\nSecond paragraph open roles"
    )
    assert extraction.normalized_text == expected_text
    assert extraction.header_span == (
        0,
        len("München Labs | Senior Engineer | Full-time | company site"),
    )
    assert extraction.body_span == (58, len(expected_text))
    assert extraction.source_fields["links"] == [
        {"anchor_text": "company site", "href": "https://example.test"},
        {"anchor_text": "open roles", "href": "https://jobs.example.test"},
    ]
    assert extraction.source_times == {"time": 1_700_000_000}


def test_no_paragraph_separator_keeps_full_text_and_unknown_spans():
    extraction = normalize_hn(
        {
            "id": "9",
            "type": "comment",
            "text": "Remote | Full-time | We build useful things",
        }
    )

    assert extraction.status == "captured"
    assert extraction.normalized_text == "Remote | Full-time | We build useful things"
    assert extraction.header_span is None
    assert extraction.body_span is None
    assert extraction.source_times == {}


def test_exclusion_precedence_is_root_then_deleted_then_dead_then_empty():
    root = normalize_hn({"id": 1, "type": "story", "deleted": True, "time": 101})
    deleted = normalize_hn({"id": 2, "type": "comment", "deleted": True, "time": 102})
    dead = normalize_hn({"id": 3, "type": "comment", "dead": True, "time": 103})
    empty = normalize_hn({"id": 4, "type": "comment", "text": "  "})
    both_flags = normalize_hn(
        {"id": 7, "type": "comment", "deleted": True, "dead": True}
    )

    assert (root.status, root.reason, root.stable_id) == ("excluded", "root_item", "1")
    assert (deleted.status, deleted.reason) == ("excluded", "deleted_item")
    assert (dead.status, dead.reason) == ("excluded", "dead_item")
    assert (empty.status, empty.reason) == ("excluded", "empty_text")
    assert (both_flags.status, both_flags.reason) == ("excluded", "deleted_item")
    assert root.source_times == {"time": 101}
    assert deleted.source_times == {"time": 102}
    assert dead.source_times == {"time": 103}


def test_html_with_no_visible_text_is_excluded_as_empty():
    extraction = normalize_hn(
        {"id": 8, "type": "comment", "text": "<script>hidden</script>"}
    )

    assert (extraction.status, extraction.reason) == ("excluded", "empty_text")


def test_malformed_payload_and_text_types_are_failed_without_raising():
    missing_type = normalize_hn({"id": 5, "text": "usable"})
    non_text = normalize_hn({"id": 6, "type": "comment", "text": 42})

    assert (missing_type.status, missing_type.reason, missing_type.stable_id) == (
        "failed",
        "malformed_payload",
        "5",
    )
    assert (non_text.status, non_text.reason, non_text.stable_id) == (
        "failed",
        "malformed_payload",
        "6",
    )


def test_malformed_source_times_fail_without_preserving_untrusted_value():
    for supplied_time in ("1700000000", True):
        extraction = normalize_hn(
            {
                "id": 10,
                "type": "comment",
                "time": supplied_time,
                "text": "Header<p>Body",
            }
        )

        assert (extraction.status, extraction.reason) == (
            "failed",
            "malformed_source_time",
        )
        assert extraction.stable_id == "10"
        assert extraction.source_times == {}


def test_valid_numeric_source_time_is_preserved_for_excluded_items():
    extraction = normalize_hn(
        {"id": 11, "type": "comment", "deleted": True, "time": 1_700_000_000}
    )

    assert (extraction.status, extraction.reason) == ("excluded", "deleted_item")
    assert extraction.source_times == {"time": 1_700_000_000}
