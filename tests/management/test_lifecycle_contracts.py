import ast
import importlib
import inspect
from pathlib import Path

ROOT = Path(__file__).parents[2] / "src/huginn/management"


def test_lifecycle_repository_contracts_expose_atomic_operations_in_exact_layers():
    contracts = {
        "persistence/contracts/repositories/account_recovery_identity": (
            "AccountRecoveryIdentityRepository",
            {
                "get_by_account_id",
                "get_by_email",
                "create",
                "set_pending_email",
                "verify_email",
            },
        ),
        "persistence/contracts/repositories/account_lifecycle_proof": (
            "AccountLifecycleProofRepository",
            {
                "get_by_digest",
                "get_by_id",
                "replace",
                "consume",
                "supersede_for_account",
            },
        ),
        "application/protocols/lifecycle_mail_outbox": (
            "LifecycleMailOutboxRepository",
            {"enqueue", "claim_due", "settle", "last_enqueued_at"},
        ),
        "application/protocols/lifecycle_throttle": (
            "LifecycleThrottleRepository",
            {"reserve"},
        ),
        "application/protocols/proof_cipher": ("ProofCipher", {"encrypt", "decrypt"}),
        "application/protocols/lifecycle_mail_sender": (
            "LifecycleMailSender",
            {"send"},
        ),
    }
    for path, (name, methods) in contracts.items():
        assert (ROOT / f"{path}.py").exists(), f"missing {path}"
        module = importlib.import_module(f"huginn.management.{path.replace('/', '.')}")
        protocol = getattr(module, name)
        assert protocol._is_protocol
        assert methods <= {
            key for key, value in vars(protocol).items() if inspect.isfunction(value)
        }
        tree = ast.parse((ROOT / f"{path}.py").read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith(
                    (
                        "huginn.management.presentation",
                        "huginn.management.persistence.row_models",
                    )
                )
                if path.startswith("persistence/contracts"):
                    assert not node.module.startswith("huginn.management.application")
