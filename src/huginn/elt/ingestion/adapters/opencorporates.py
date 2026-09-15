"""OpenCorporates adapter. See architecture document section 5.

Enrichment-only: this adapter looks up companies Huginn already knows
about (a name list handed in by the caller, see
`src/huginn/elt/ingestion/__main__.py`), it does not discover new ones.
Mechanism: "api" (`companies/search`, a structured JSON endpoint), not a
scrape. Fetch-plan decisions: architecture-notes/opencorporates-fetch-plan.md
(KAN-53, KAN-54).

The Bronze payload is copied from the matched company object and excludes
the source's `officers` field because it may contain personal data.

The response envelope this adapter parses (`results.companies[].company`)
is a documented OpenCorporates convention, not independently live-verified
(no API token was registered for the KAN-53 design session) — see the flag
at the top of the fetch-plan. Every access to that shape is isolated behind
`_extract_companies` so a shape correction is a one-function fix.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable

import requests

from huginn.elt.ingestion.models import RawRecord
from huginn.elt.ingestion.ports import ApiSourcePort

logger = logging.getLogger(__name__)

API_BASE_URL = "https://api.opencorporates.com/v0.4"
API_TOKEN_ENV_VAR = "HUGINN_OPENCORPORATES_API_TOKEN"
REQUEST_TIMEOUT_SECONDS = 10.0


class OpenCorporatesRequestError(RuntimeError):
    """A sanitized OpenCorporates request failure safe to log."""


def _api_token() -> str:
    """Read the OpenCorporates API token from
    `HUGINN_OPENCORPORATES_API_TOKEN`.

    Unlike YC's public, search-only Algolia key (`yc.py`'s
    `_algolia_api_key`), this is not shipped to any public frontend: every
    call requires a real, registered OpenCorporates account token
    (docs/sources/opencorporates-api.md, Access).
    """
    api_token = os.environ.get(API_TOKEN_ENV_VAR)
    if not api_token:
        raise RuntimeError(
            f"{API_TOKEN_ENV_VAR} is not set. Copy .env.example to .env "
            "and fill in a registered OpenCorporates API account token."
        )
    return api_token


def _search_companies(name: str) -> dict:
    """GET one `companies/search` call for `name` and return the parsed
    response body. See docs/sources/opencorporates-api.md, Access +
    Response shape; architecture-notes/opencorporates-fetch-plan.md
    section 2.
    """
    api_token = _api_token()
    response = None
    try:
        response = requests.get(
            f"{API_BASE_URL}/companies/search",
            params={"q": name, "api_token": api_token},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        if isinstance(exc, requests.HTTPError):
            status_code = getattr(response, "status_code", None)
            failure = (
                f"HTTP {status_code}" if isinstance(status_code, int) else "HTTP error"
            )
        else:
            failure = type(exc).__name__
        raise OpenCorporatesRequestError(
            f"OpenCorporates company search failed: {failure}"
        ) from None


def _extract_companies(search_response: dict) -> list[dict]:
    """Unwrap OpenCorporates' documented `results.companies[].company`-
    wrapped search response envelope into a flat list of company objects.

    The only place this response shape is touched: see the module
    docstring and architecture-notes/opencorporates-fetch-plan.md section 2
    for why this isolation matters (the shape is a documented convention,
    not live-verified).
    """
    return [entry["company"] for entry in search_response["results"]["companies"]]


def _company_record(company: dict) -> RawRecord:
    """Build a Bronze record without retaining OpenCorporates officers.

    Copying before removal keeps the parsed API response available to the
    caller while ensuring the payload handed to Bronze is privacy-safe.
    """
    jurisdiction_code = company["jurisdiction_code"]
    company_number = company["company_number"]
    if not jurisdiction_code or not company_number:
        raise ValueError("company identity fields must be non-empty")
    stable_id = f"{jurisdiction_code}:{company_number}"
    payload = company.copy()
    payload.pop("officers", None)
    return RawRecord(stable_id=stable_id, payload=payload)


def _extract_company_records(search_response: dict) -> list[RawRecord]:
    """Convert company wrappers into Bronze-ready records.

    The company object remains otherwise close to the source payload, while
    the source-native jurisdiction and company number form its stable
    identifier. Privacy-sensitive officer data is excluded by
    `_company_record` before persistence.
    """
    return [_company_record(company) for company in _extract_companies(search_response)]


class OpenCorporatesAdapter(ApiSourcePort):
    source = "opencorporates"
    mechanism = "api"
    stable_fields = ("current_status", "dissolution_date", "updated_at")

    def __init__(self, company_loader: Callable[[], list[str]], max_calls: int) -> None:
        """`company_loader` supplies the company names to search at fetch time.

        The adapter does not decide which companies to enrich; the loader is
        injected by `src/huginn/elt/ingestion/__main__.py`. Deferring the call
        until `fetch()` keeps service construction free of database I/O.
        `max_calls` caps how many searches this fetch makes, a simple per-run
        budget rather than the stateful cross-run quota tracker
        architecture-notes/opencorporates-fetch-plan.md section 7
        explicitly defers.
        """
        self._company_loader = company_loader
        self._max_calls = max_calls

    def fetch(self) -> list[RawRecord]:
        """Search for each company name in turn, up to `max_calls`
        searches, and enrich exactly the ones with an unambiguous match.

        Per architecture-notes/opencorporates-fetch-plan.md section 3: a
        search returning exactly one result enriches that company (one
        `RawRecord`). Zero results or more than one result skips it this
        run, no guess, no partial-confidence fallback, just an INFO log
        naming why. A skipped company is not lost: it stays selected by
        the next run's Gold read (section 5) until it resolves to exactly
        one hit or the run budget is spent trying.
        """
        records = []
        seen_stable_ids = set()
        for name in self._company_loader()[: self._max_calls]:
            response = _search_companies(name)
            try:
                companies = _extract_companies(response)
            except KeyError, TypeError, ValueError:
                logger.warning(
                    "opencorporates fetch: skipping %r, malformed search response",
                    name,
                )
                continue
            if len(companies) != 1:
                logger.info(
                    "opencorporates fetch: skipping %r, %d search results "
                    "(need exactly 1 to enrich unambiguously)",
                    name,
                    len(companies),
                )
                continue
            try:
                record = _company_record(companies[0])
            except KeyError, TypeError, ValueError:
                logger.warning(
                    "opencorporates fetch: skipping %r, malformed company record",
                    name,
                )
                continue
            if record.stable_id in seen_stable_ids:
                logger.info(
                    "opencorporates fetch: skipping %r, duplicate stable ID %r",
                    name,
                    record.stable_id,
                )
                continue
            seen_stable_ids.add(record.stable_id)
            records.append(record)
        return records
