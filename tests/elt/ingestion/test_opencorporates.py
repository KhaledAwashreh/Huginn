from __future__ import annotations

import logging

import pytest
import requests

from huginn.elt.ingestion.adapters import opencorporates
from huginn.elt.ingestion.models import RawRecord
from huginn.elt.ingestion.ports import ApiSourcePort


def test_opencorporates_adapter_explicitly_implements_api_source_port():
    """The adapter explicitly inherits the API source contract."""
    assert ApiSourcePort in opencorporates.OpenCorporatesAdapter.__mro__


def test_opencorporates_adapter_source_and_mechanism():
    """The adapter identifies its source and API ingestion mechanism."""
    adapter = opencorporates.OpenCorporatesAdapter(
        company_loader=lambda: [], max_calls=1
    )
    assert adapter.source == "opencorporates"
    assert adapter.mechanism == "api"


def test_api_token_reads_env_var(monkeypatch):
    """Token lookup returns the configured OpenCorporates credential."""
    monkeypatch.setenv(opencorporates.API_TOKEN_ENV_VAR, "test-token")

    assert opencorporates._api_token() == "test-token"


def test_api_token_raises_when_unset(monkeypatch):
    """Token lookup rejects a missing environment variable."""
    monkeypatch.delenv(opencorporates.API_TOKEN_ENV_VAR, raising=False)

    try:
        opencorporates._api_token()
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert opencorporates.API_TOKEN_ENV_VAR in str(exc)


def test_api_token_raises_when_empty(monkeypatch):
    """Token lookup rejects an explicitly empty environment variable."""
    monkeypatch.setenv(opencorporates.API_TOKEN_ENV_VAR, "")

    try:
        opencorporates._api_token()
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert opencorporates.API_TOKEN_ENV_VAR in str(exc)


def test_search_companies_requests_expected_url_params_and_timeout(monkeypatch):
    """Company search sends the documented URL, parameters, and timeout."""
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            """Represent a successful HTTP status."""
            return None

        def json(self):
            """Return a minimal valid company-search response."""
            return {"results": {"companies": []}}

    def fake_get(url, params, timeout):
        """Capture the outgoing request contract for assertions."""
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(opencorporates.requests, "get", fake_get)
    monkeypatch.setenv(opencorporates.API_TOKEN_ENV_VAR, "test-token")

    result = opencorporates._search_companies("Acme Robotics")

    assert captured["url"] == f"{opencorporates.API_BASE_URL}/companies/search"
    assert captured["params"] == {"q": "Acme Robotics", "api_token": "test-token"}
    assert captured["timeout"] == opencorporates.REQUEST_TIMEOUT_SECONDS
    assert result == {"results": {"companies": []}}


def test_search_companies_raises_on_non_2xx_response(monkeypatch):
    """Company search exposes a sanitized error for non-success statuses."""

    class FakeResponse:
        status_code = 403

        def raise_for_status(self):
            """Raise the HTTP failure returned by the provider."""
            raise requests.HTTPError(
                "403 Forbidden for url: "
                "https://api.opencorporates.com/v0.4/companies/search?"
                "q=Acme&api_token=test-token"
            )

        def json(self):
            """Fail if parsing is attempted after status validation fails."""
            raise AssertionError(
                "json() must not be called after raise_for_status raises"
            )

    monkeypatch.setattr(
        opencorporates.requests, "get", lambda url, params, timeout: FakeResponse()
    )
    monkeypatch.setenv(opencorporates.API_TOKEN_ENV_VAR, "test-token")

    try:
        opencorporates._search_companies("Acme Robotics")
        raise AssertionError("expected OpenCorporatesRequestError")
    except opencorporates.OpenCorporatesRequestError as exc:
        assert "HTTP 403" in str(exc)
        assert "test-token" not in str(exc)


def test_search_companies_sanitizes_request_exceptions(monkeypatch):
    """Transport errors do not leak the API token into raised messages."""

    def fake_get(url, params, timeout):
        """Raise a transport error containing a token-bearing request URL."""
        raise requests.ConnectionError(
            f"failed for {url}?q=Acme&api_token={params['api_token']}"
        )

    monkeypatch.setattr(opencorporates.requests, "get", fake_get)
    monkeypatch.setenv(opencorporates.API_TOKEN_ENV_VAR, "test-token")

    try:
        opencorporates._search_companies("Acme Robotics")
        raise AssertionError("expected OpenCorporatesRequestError")
    except opencorporates.OpenCorporatesRequestError as exc:
        assert "ConnectionError" in str(exc)
        assert "test-token" not in str(exc)


def test_search_companies_sanitizes_malformed_json(monkeypatch):
    """Malformed JSON errors do not leak the API token."""

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            """Represent a successful HTTP status before JSON parsing."""
            return None

        def json(self):
            """Raise a decoder error containing a token-bearing URL."""
            raise requests.exceptions.JSONDecodeError(
                "malformed response",
                "https://api.opencorporates.com/v0.4/companies/search?"
                "q=Acme&api_token=test-token",
                0,
            )

    monkeypatch.setattr(
        opencorporates.requests, "get", lambda url, params, timeout: FakeResponse()
    )
    monkeypatch.setenv(opencorporates.API_TOKEN_ENV_VAR, "test-token")

    try:
        opencorporates._search_companies("Acme Robotics")
        raise AssertionError("expected OpenCorporatesRequestError")
    except opencorporates.OpenCorporatesRequestError as exc:
        assert "JSONDecodeError" in str(exc)
        assert "test-token" not in str(exc)


def test_search_companies_raises_when_api_token_missing(monkeypatch):
    """Company search fails before HTTP I/O when its token is missing."""
    monkeypatch.delenv(opencorporates.API_TOKEN_ENV_VAR, raising=False)

    try:
        opencorporates._search_companies("Acme Robotics")
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert opencorporates.API_TOKEN_ENV_VAR in str(exc)


def test_extract_company_records_unwraps_the_company_wrapped_list():
    """Wrapped provider companies become Bronze-ready records."""
    response = {
        "results": {
            "companies": [
                {
                    "company": {
                        "name": "Acme Robotics",
                        "jurisdiction_code": "gb",
                        "company_number": "123",
                    }
                },
                {
                    "company": {
                        "name": "Acme Robotics Ltd",
                        "jurisdiction_code": "us_de",
                        "company_number": "456",
                    }
                },
            ]
        }
    }

    records = opencorporates._extract_company_records(response)

    assert records == [
        RawRecord(
            stable_id="gb:123",
            payload={
                "name": "Acme Robotics",
                "jurisdiction_code": "gb",
                "company_number": "123",
            },
        ),
        RawRecord(
            stable_id="us_de:456",
            payload={
                "name": "Acme Robotics Ltd",
                "jurisdiction_code": "us_de",
                "company_number": "456",
            },
        ),
    ]


def test_extract_company_records_returns_empty_list_when_no_companies():
    """An empty provider result produces no Bronze records."""
    response = {"results": {"companies": []}}

    assert opencorporates._extract_company_records(response) == []


def test_fetch_builds_one_record_when_search_returns_exactly_one_match(monkeypatch):
    """Exactly one search match produces one company record."""
    company = {
        "name": "Acme Robotics",
        "jurisdiction_code": "us_de",
        "company_number": "1234567",
    }

    def fake_search_companies(name):
        """Return the one unambiguous company fixture."""
        return {"results": {"companies": [{"company": company}]}}

    monkeypatch.setattr(opencorporates, "_search_companies", fake_search_companies)

    records = opencorporates.OpenCorporatesAdapter(
        company_loader=lambda: ["Acme Robotics"], max_calls=5
    ).fetch()

    assert records == [RawRecord(stable_id="us_de:1234567", payload=company)]


def test_fetch_skips_a_company_with_zero_search_results(monkeypatch, caplog):
    """A zero-result search is logged and produces no record."""
    monkeypatch.setattr(
        opencorporates,
        "_search_companies",
        lambda name: {"results": {"companies": []}},
    )

    with caplog.at_level(logging.INFO, logger=opencorporates.logger.name):
        records = opencorporates.OpenCorporatesAdapter(
            company_loader=lambda: ["Nonexistent Co"], max_calls=5
        ).fetch()

    assert records == []
    infos = [r for r in caplog.records if r.levelno == logging.INFO]
    assert any("Nonexistent Co" in r.getMessage() for r in infos)


def test_fetch_skips_a_company_with_more_than_one_search_result(monkeypatch, caplog):
    """An ambiguous search is logged and produces no record."""
    monkeypatch.setattr(
        opencorporates,
        "_search_companies",
        lambda name: {
            "results": {
                "companies": [
                    {"company": {"name": "Acme", "company_number": "1"}},
                    {"company": {"name": "Acme Inc", "company_number": "2"}},
                ]
            }
        },
    )

    with caplog.at_level(logging.INFO, logger=opencorporates.logger.name):
        records = opencorporates.OpenCorporatesAdapter(
            company_loader=lambda: ["Acme"], max_calls=5
        ).fetch()

    assert records == []
    infos = [r for r in caplog.records if r.levelno == logging.INFO]
    assert any("Acme" in r.getMessage() for r in infos)


def test_fetch_payload_excludes_officers_without_mutating_api_response(monkeypatch):
    """Bronze payloads omit officers without mutating provider data."""
    company = {
        "name": "Acme Robotics",
        "jurisdiction_code": "gb",
        "company_number": "999",
        "officers": [{"name": "Jane Doe"}],
    }
    monkeypatch.setattr(
        opencorporates,
        "_search_companies",
        lambda name: {"results": {"companies": [{"company": company}]}},
    )

    records = opencorporates.OpenCorporatesAdapter(
        company_loader=lambda: ["Acme Robotics"], max_calls=5
    ).fetch()

    assert records[0].payload == {
        "name": "Acme Robotics",
        "jurisdiction_code": "gb",
        "company_number": "999",
    }
    assert "officers" not in records[0].payload
    assert company["officers"] == [{"name": "Jane Doe"}]
    assert records[0].payload is not company


def test_fetch_stable_id_is_jurisdiction_code_and_company_number(monkeypatch):
    """Stable IDs combine the source jurisdiction and company number."""
    company = {
        "name": "Acme Robotics",
        "jurisdiction_code": "us_de",
        "company_number": "1234567",
    }
    monkeypatch.setattr(
        opencorporates,
        "_search_companies",
        lambda name: {"results": {"companies": [{"company": company}]}},
    )

    records = opencorporates.OpenCorporatesAdapter(
        company_loader=lambda: ["Acme Robotics"], max_calls=5
    ).fetch()

    assert records[0].stable_id == "us_de:1234567"


def test_fetch_deduplicates_matching_stable_ids_across_company_names(monkeypatch):
    """Different searches cannot emit the same stable company twice."""
    shared_company = {
        "name": "Acme Robotics",
        "jurisdiction_code": "gb",
        "company_number": "123",
    }
    monkeypatch.setattr(
        opencorporates,
        "_search_companies",
        lambda name: {"results": {"companies": [{"company": shared_company}]}},
    )

    records = opencorporates.OpenCorporatesAdapter(
        company_loader=lambda: ["Acme Robotics", "Acme Robotics Ltd"], max_calls=5
    ).fetch()

    assert records == [RawRecord(stable_id="gb:123", payload=shared_company)]


def test_fetch_stops_after_max_calls(monkeypatch):
    """Fetch respects its per-run provider-call budget."""
    call_count = {"n": 0}

    def fake_search_companies(name):
        """Count each company search while returning no matches."""
        call_count["n"] += 1
        return {"results": {"companies": []}}

    monkeypatch.setattr(opencorporates, "_search_companies", fake_search_companies)

    opencorporates.OpenCorporatesAdapter(
        company_loader=lambda: ["A", "B", "C", "D"], max_calls=2
    ).fetch()

    assert call_count["n"] == 2


def test_fetch_returns_empty_list_when_companies_list_is_empty(monkeypatch):
    """An empty candidate loader avoids all provider searches."""

    def _unexpected_search(name):
        """Fail if fetch searches without any candidate companies."""
        raise AssertionError("_search_companies should not be called")

    monkeypatch.setattr(opencorporates, "_search_companies", _unexpected_search)

    assert (
        opencorporates.OpenCorporatesAdapter(
            company_loader=lambda: [], max_calls=5
        ).fetch()
        == []
    )


def test_fetch_skips_a_malformed_response_and_continues(monkeypatch, caplog):
    """A malformed match is logged without blocking later candidates."""
    good_company = {
        "name": "Good Co",
        "jurisdiction_code": "gb",
        "company_number": "42",
    }

    def fake_search_companies(name):
        """Return one malformed match followed by a valid match."""
        if name == "Malformed Co":
            return {"results": {"companies": [{"company": {"name": name}}]}}
        return {"results": {"companies": [{"company": good_company}]}}

    monkeypatch.setattr(opencorporates, "_search_companies", fake_search_companies)

    with caplog.at_level(logging.WARNING, logger=opencorporates.logger.name):
        records = opencorporates.OpenCorporatesAdapter(
            company_loader=lambda: ["Malformed Co", "Good Co"], max_calls=2
        ).fetch()

    assert records == [RawRecord(stable_id="gb:42", payload=good_company)]
    assert "Malformed Co" in caplog.text


@pytest.mark.parametrize(
    "malformed_company",
    [
        {
            "name": "Empty Jurisdiction Co",
            "jurisdiction_code": "",
            "company_number": "1",
        },
        {"name": "Empty Number Co", "jurisdiction_code": "gb", "company_number": ""},
    ],
)
def test_fetch_skips_empty_company_identity_and_continues(
    monkeypatch, caplog, malformed_company
):
    """Empty stable-ID components do not block later valid candidates."""
    good_company = {
        "name": "Good Co",
        "jurisdiction_code": "gb",
        "company_number": "42",
    }

    def fake_search_companies(name):
        """Return the parameterized malformed company or a valid company."""
        company = (
            malformed_company if name == malformed_company["name"] else good_company
        )
        return {"results": {"companies": [{"company": company}]}}

    monkeypatch.setattr(opencorporates, "_search_companies", fake_search_companies)

    with caplog.at_level(logging.WARNING, logger=opencorporates.logger.name):
        records = opencorporates.OpenCorporatesAdapter(
            company_loader=lambda: [malformed_company["name"], "Good Co"], max_calls=2
        ).fetch()

    assert records == [RawRecord(stable_id="gb:42", payload=good_company)]
    assert malformed_company["name"] in caplog.text
