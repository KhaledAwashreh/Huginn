from __future__ import annotations

import logging

import requests

from huginn.elt.ingestion.adapters import opencorporates
from huginn.elt.ingestion.models import RawRecord
from huginn.elt.ingestion.ports import ApiSourcePort


def test_opencorporates_adapter_explicitly_implements_api_source_port():
    assert ApiSourcePort in opencorporates.OpenCorporatesAdapter.__mro__


def test_opencorporates_adapter_source_and_mechanism():
    adapter = opencorporates.OpenCorporatesAdapter(companies=[], max_calls=1)
    assert adapter.source == "opencorporates"
    assert adapter.mechanism == "api"


def test_api_token_reads_env_var(monkeypatch):
    monkeypatch.setenv(opencorporates.API_TOKEN_ENV_VAR, "test-token")

    assert opencorporates._api_token() == "test-token"


def test_api_token_raises_when_unset(monkeypatch):
    monkeypatch.delenv(opencorporates.API_TOKEN_ENV_VAR, raising=False)

    try:
        opencorporates._api_token()
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert opencorporates.API_TOKEN_ENV_VAR in str(exc)


def test_api_token_raises_when_empty(monkeypatch):
    monkeypatch.setenv(opencorporates.API_TOKEN_ENV_VAR, "")

    try:
        opencorporates._api_token()
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert opencorporates.API_TOKEN_ENV_VAR in str(exc)


def test_search_companies_requests_expected_url_params_and_timeout(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"results": {"companies": []}}

    def fake_get(url, params, timeout):
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
    class FakeResponse:
        def raise_for_status(self):
            raise requests.HTTPError("403 Forbidden")

        def json(self):
            raise AssertionError(
                "json() must not be called after raise_for_status raises"
            )

    monkeypatch.setattr(
        opencorporates.requests, "get", lambda url, params, timeout: FakeResponse()
    )
    monkeypatch.setenv(opencorporates.API_TOKEN_ENV_VAR, "test-token")

    try:
        opencorporates._search_companies("Acme Robotics")
        raise AssertionError("expected requests.HTTPError")
    except requests.HTTPError:
        pass


def test_search_companies_raises_when_api_token_missing(monkeypatch):
    monkeypatch.delenv(opencorporates.API_TOKEN_ENV_VAR, raising=False)

    try:
        opencorporates._search_companies("Acme Robotics")
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert opencorporates.API_TOKEN_ENV_VAR in str(exc)


def test_extract_companies_unwraps_the_company_wrapped_list():
    response = {
        "results": {
            "companies": [
                {"company": {"name": "Acme Robotics", "company_number": "123"}},
                {"company": {"name": "Acme Robotics Ltd", "company_number": "456"}},
            ]
        }
    }

    companies = opencorporates._extract_companies(response)

    assert companies == [
        {"name": "Acme Robotics", "company_number": "123"},
        {"name": "Acme Robotics Ltd", "company_number": "456"},
    ]


def test_extract_companies_returns_empty_list_when_no_companies():
    response = {"results": {"companies": []}}

    assert opencorporates._extract_companies(response) == []


def test_fetch_builds_one_record_when_search_returns_exactly_one_match(monkeypatch):
    company = {
        "name": "Acme Robotics",
        "jurisdiction_code": "us_de",
        "company_number": "1234567",
    }

    def fake_search_companies(name):
        return {"results": {"companies": [{"company": company}]}}

    monkeypatch.setattr(opencorporates, "_search_companies", fake_search_companies)

    records = opencorporates.OpenCorporatesAdapter(
        companies=["Acme Robotics"], max_calls=5
    ).fetch()

    assert records == [RawRecord(stable_id="us_de:1234567", payload=company)]


def test_fetch_skips_a_company_with_zero_search_results(monkeypatch, caplog):
    monkeypatch.setattr(
        opencorporates,
        "_search_companies",
        lambda name: {"results": {"companies": []}},
    )

    with caplog.at_level(logging.INFO, logger=opencorporates.logger.name):
        records = opencorporates.OpenCorporatesAdapter(
            companies=["Nonexistent Co"], max_calls=5
        ).fetch()

    assert records == []
    infos = [r for r in caplog.records if r.levelno == logging.INFO]
    assert any("Nonexistent Co" in r.getMessage() for r in infos)


def test_fetch_skips_a_company_with_more_than_one_search_result(monkeypatch, caplog):
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
            companies=["Acme"], max_calls=5
        ).fetch()

    assert records == []
    infos = [r for r in caplog.records if r.levelno == logging.INFO]
    assert any("Acme" in r.getMessage() for r in infos)


def test_fetch_payload_is_the_matched_company_object_unmodified(monkeypatch):
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
        companies=["Acme Robotics"], max_calls=5
    ).fetch()

    assert records[0].payload == company
    assert records[0].payload is company


def test_fetch_stable_id_is_jurisdiction_code_and_company_number(monkeypatch):
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
        companies=["Acme Robotics"], max_calls=5
    ).fetch()

    assert records[0].stable_id == "us_de:1234567"


def test_fetch_stops_after_max_calls(monkeypatch):
    call_count = {"n": 0}

    def fake_search_companies(name):
        call_count["n"] += 1
        return {"results": {"companies": []}}

    monkeypatch.setattr(opencorporates, "_search_companies", fake_search_companies)

    opencorporates.OpenCorporatesAdapter(
        companies=["A", "B", "C", "D"], max_calls=2
    ).fetch()

    assert call_count["n"] == 2


def test_fetch_returns_empty_list_when_companies_list_is_empty(monkeypatch):
    def _unexpected_search(name):
        raise AssertionError("_search_companies should not be called")

    monkeypatch.setattr(opencorporates, "_search_companies", _unexpected_search)

    assert opencorporates.OpenCorporatesAdapter(companies=[], max_calls=5).fetch() == []
