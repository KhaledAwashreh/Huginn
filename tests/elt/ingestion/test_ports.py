from __future__ import annotations

from huginn.elt.ingestion import models, ports


def test_api_source_port_extends_source_port():
    assert ports.SourcePort in ports.ApiSourcePort.__mro__


def test_web_scrape_source_port_extends_source_port():
    assert ports.SourcePort in ports.WebScrapeSourcePort.__mro__


def test_newsletter_source_port_extends_source_port():
    assert ports.SourcePort in ports.NewsletterSourcePort.__mro__


def test_api_source_port_adds_no_new_methods_beyond_fetch():
    assert not hasattr(ports.ApiSourcePort, "fetch_page")
    assert not hasattr(ports.ApiSourcePort, "fetch_issue")
    assert hasattr(ports.ApiSourcePort, "fetch")


def test_web_scrape_source_port_declares_fetch_page():
    assert hasattr(ports.WebScrapeSourcePort, "fetch_page")
    assert hasattr(ports.WebScrapeSourcePort, "fetch")


def test_newsletter_source_port_declares_fetch_issue():
    assert hasattr(ports.NewsletterSourcePort, "fetch_issue")
    assert hasattr(ports.NewsletterSourcePort, "fetch")


def test_source_port_base_shape_unchanged():
    assert hasattr(ports.SourcePort, "fetch")
    assert not hasattr(ports.SourcePort, "fetch_page")
    assert not hasattr(ports.SourcePort, "fetch_issue")


def test_raw_record_unchanged():
    record = models.RawRecord(stable_id="1", payload={"a": 1})
    assert record.stable_id == "1"
    assert record.payload == {"a": 1}
