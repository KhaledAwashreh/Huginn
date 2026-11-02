"""HTTP transport guarantees shared by EU-Startups discovery and enrichment."""

import pytest
from curl_cffi.requests.exceptions import ConnectionError, SSLError, Timeout

from huginn.elt.ingestion.adapters import eu_startups, eu_startups_enrichment


@pytest.mark.parametrize("module", [eu_startups, eu_startups_enrichment])
def test_eu_startups_uses_verified_browser_transport_without_redirects(
    monkeypatch, module
):
    captured = {}

    class Response:
        status_code = 200
        text = "<html>raw source content</html>"

        def raise_for_status(self):
            pass

    def get(url, **kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(module.requests, "get", get)
    adapter = (
        module.EuStartupsDiscoveryAdapter(timeout=7)
        if module is eu_startups
        else module.EuStartupsEnrichmentAdapter(lambda: [], max_calls=1, timeout=7)
    )
    assert (
        adapter.fetch_page("https://www.eu-startups.com/directory/brightroom/")
        == Response.text
    )
    assert captured["impersonate"] == "chrome"
    assert captured["verify"] is True
    assert captured["allow_redirects"] is False
    assert captured["timeout"] == 7
    assert "headers" not in captured


@pytest.mark.parametrize("module", [eu_startups, eu_startups_enrichment])
@pytest.mark.parametrize("failure", [ConnectionError, SSLError, Timeout])
def test_native_browser_transport_failures_remain_sanitized(
    monkeypatch, module, failure
):
    def fail(*args, **kwargs):
        raise failure("private-request-details")

    monkeypatch.setattr(module.requests, "get", fail)
    if module is eu_startups:
        adapter = module.EuStartupsDiscoveryAdapter()
        error_type = module.EuStartupsFetchError
    else:
        adapter = module.EuStartupsEnrichmentAdapter(lambda: [], max_calls=1)
        error_type = module.EuStartupsEnrichmentFetchError
    with pytest.raises(error_type) as error:
        adapter.fetch_page("https://www.eu-startups.com/directory/brightroom/")
    assert "private-request-details" not in str(error.value)
    assert failure.__name__ in str(error.value)
    assert error.value.__suppress_context__
