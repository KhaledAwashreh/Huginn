from huginn.elt.silver.resolution import normalize_domain


def test_normalize_domain_strips_protocol_and_www():
    assert normalize_domain("https://www.Acme.AI/careers") == "acme.ai"


def test_normalize_domain_handles_bare_domain():
    assert normalize_domain("acme.ai") == "acme.ai"


def test_normalize_domain_strips_trailing_path():
    assert normalize_domain("http://acme.ai/jobs/backend-engineer") == "acme.ai"


def test_normalize_domain_strips_port():
    assert normalize_domain("https://greenhouse.io:443/jobs") == "greenhouse.io"


def test_normalize_domain_strips_userinfo():
    assert normalize_domain("https://user@greenhouse.io/jobs") == "greenhouse.io"


def test_normalize_domain_strips_userinfo_and_port_together():
    assert (
        normalize_domain("https://user:pass@greenhouse.io:8080/jobs") == "greenhouse.io"
    )
