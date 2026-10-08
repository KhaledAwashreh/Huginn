"""Enforce the management dependency direction from its source import graph."""

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2] / "src/huginn/management"
LAYERS = {
    "presentation",
    "application",
    "domain",
    "persistence",
    "security",
    "delivery",
}


def _imports(path, root=ROOT):
    module = "huginn.management." + ".".join(
        path.relative_to(root).with_suffix("").parts
    )
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = module.split(".")[: -node.level]
                yield ".".join(parts + ([node.module] if node.module else []))
            elif node.module:
                yield node.module
                if node.module == "huginn.management":
                    yield from (node.module + "." + alias.name for alias in node.names)


def test_management_has_explicit_layers_and_no_legacy_packages():
    roots = {
        path.name
        for path in ROOT.iterdir()
        if path.is_dir() and path.name != "__pycache__"
    }
    assert roots == LAYERS
    assert (ROOT / "persistence/contracts/database.py").is_file()
    assert (ROOT / "persistence/contracts/unit_of_work.py").is_file()
    assert (ROOT / "presentation/cli/account_admin.py").is_file()


def _within(module, packages):
    return any(
        module == package or module.startswith(package + ".") for package in packages
    )


def _allowed_import(relative, imported):
    layer = relative.parts[0]
    root = imported.split(".")[0]
    local = imported.removeprefix("huginn.management.")
    management = imported.startswith("huginn.management.")
    if root == "psycopg":
        return relative.as_posix() == "persistence/database/client.py"
    if layer == "domain":
        return root in sys.stdlib_module_names or _within(local, ("domain",))
    if layer == "security":
        return root not in {"fastapi", "starlette", "pydantic"} and (
            not management
            or _within(local, ("security",))
            or (
                relative.as_posix() == "security/encrypted_proof_cipher.py"
                and local
                in {
                    "application.protocols.proof_cipher",
                    "application.read_models.lifecycle_mail_message",
                }
            )
        )
    if layer == "delivery":
        return root not in {"fastapi", "starlette", "pydantic"} and (
            not management
            or _within(
                local,
                (
                    "delivery",
                    "application.protocols",
                    "application.read_models",
                    "application.constants",
                ),
            )
            or local == "config"
        )
    if layer == "application":
        return root not in {"fastapi", "starlette", "pydantic"} and (
            not management
            or _within(
                local, ("application", "domain", "security", "persistence.contracts")
            )
            or local == "config"
        )
    if layer == "presentation":
        return (
            not management
            or _within(
                local,
                (
                    "presentation",
                    "application",
                    "domain",
                    "security",
                    "persistence.contracts",
                    "persistence.errors",
                ),
            )
            or local == "config"
            or (
                relative.as_posix() == "presentation/cli/lifecycle_mail_worker.py"
                and _within(
                    local,
                    ("persistence.database", "persistence.repositories", "delivery"),
                )
            )
        )
    if layer == "persistence":
        section = relative.parts[1]
        allowed_packages = {
            "contracts": ("persistence.contracts", "persistence.errors", "domain"),
            "repositories": (
                "application.protocols",
                "application.read_models",
                "persistence.repositories",
                "persistence.contracts",
                "persistence.row_models",
                "persistence.errors",
                "domain",
            ),
            "database": (
                "persistence.database",
                "persistence.contracts",
                "persistence.errors",
            ),
            "row_models": (
                "persistence.row_models",
                "persistence.contracts",
                "persistence.errors",
                "domain",
            ),
            "errors": ("persistence.errors",),
        }.get(section, ())
        if root in {"fastapi", "starlette"}:
            return False
        if (
            section == "contracts"
            and root not in sys.stdlib_module_names
            and not management
        ):
            return False
        return not management or _within(local, allowed_packages)
    return True


def _graph_violations(root):
    violations = []
    for path in root.rglob("*.py"):
        relative = path.relative_to(root)
        for imported in _imports(path, root):
            if not _allowed_import(relative, imported):
                violations.append(f"{relative}: {imported}")
    return violations


def test_management_import_graph_points_downward():
    assert _graph_violations(ROOT) == []


@pytest.mark.parametrize(
    ("path", "imported"),
    (
        (
            "persistence/contracts/repositories/account.py",
            "huginn.management.persistence.database.client",
        ),
        (
            "persistence/contracts/repositories/account.py",
            "huginn.management.persistence.repositories.account",
        ),
        (
            "persistence/repositories/account.py",
            "huginn.management.persistence.database.client",
        ),
        (
            "persistence/database/client.py",
            "huginn.management.persistence.repositories.account",
        ),
        (
            "application/services/account.py",
            "huginn.management.persistence.repositories.account",
        ),
        (
            "presentation/api/routers/account.py",
            "huginn.management.persistence.database.client",
        ),
        ("domain/entities/account.py", "pydantic"),
        ("security/tokens.py", "psycopg"),
        (
            "domain/entities/account.py",
            "huginn.management.application.read_models.account_security",
        ),
        ("security/tokens.py", "huginn.management.application.services.signup_service"),
        (
            "delivery/smtp_lifecycle_mail_sender.py",
            "huginn.management.presentation.api.requests.signup",
        ),
    ),
)
def test_import_graph_rejects_forbidden_edges(tmp_path, path, imported):
    source = tmp_path / path
    source.parent.mkdir(parents=True)
    source.write_text(f"import {imported}\n")
    assert _graph_violations(tmp_path) == [f"{path}: {imported}"]


def test_package_initializers_do_not_reexport_surfaces():
    for path in ROOT.rglob("__init__.py"):
        assert not list(_imports(path)), path
