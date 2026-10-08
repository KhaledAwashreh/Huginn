import hashlib
import importlib
from pathlib import Path

import pytest


def _proofs():
    path = (
        Path(__file__).parents[2] / "src/huginn/management/security/lifecycle_proofs.py"
    )
    assert path.exists(), "lifecycle proof generation is missing"
    return importlib.import_module("huginn.management.security.lifecycle_proofs")


def test_lifecycle_proofs_have_256_bits_and_store_only_digests():
    import base64

    proofs = _proofs()
    tokens = {proofs.generate_lifecycle_proof() for _ in range(20)}
    assert len(tokens) == 20
    for token in tokens:
        assert len(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))) >= 32
        digest = proofs.digest_lifecycle_proof(token)
        assert digest == hashlib.sha256(token.encode("ascii")).hexdigest()
        assert token not in digest


@pytest.mark.parametrize("token", [None, "", "bad token", "\N{SNOWMAN}", "x" * 1025])
def test_malformed_lifecycle_proofs_are_rejected_without_echoing(token):
    proofs = _proofs()
    with pytest.raises(ValueError, match="invalid lifecycle proof") as error:
        proofs.digest_lifecycle_proof(token)
    if token:
        assert token not in str(error.value)
