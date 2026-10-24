from __future__ import annotations

import ast
from pathlib import Path

SILVER = Path(__file__).parents[4] / "src" / "huginn" / "elt" / "silver"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_pure_layers_do_not_import_repositories_or_presentation() -> None:
    pure_dirs = ("models", "normalizers", "policies", "types", "constants")
    forbidden = ("huginn.elt.silver.repositories", "huginn.elt.silver.presentation")
    violations = []
    for directory in pure_dirs:
        for path in (SILVER / directory).glob("*.py"):
            for imported in _imports(path):
                if (
                    imported.startswith(forbidden)
                    or imported in {"requests", "socket"}
                    or imported.startswith(
                        (
                            "huginn.elt.silver.resolution",
                            "huginn.elt.silver.eu_startups_staging",
                            "huginn.elt.ingestion.adapters",
                        )
                    )
                ):
                    violations.append(f"{path.relative_to(SILVER)} imports {imported}")
    assert not violations, (
        "pure Silver modules crossed an outer dependency boundary: "
        + "; ".join(violations)
    )


def test_application_services_depend_on_repository_protocols() -> None:
    expected = {
        "services/source_context.py": "huginn.elt.silver.repositories.protocols.source_context_repository",
        "services/source_currentness.py": "huginn.elt.silver.repositories.protocols.source_currentness_repository",
    }
    violations = []
    for relative, protocol_module in expected.items():
        modules = _imports(SILVER / relative)
        if protocol_module not in modules:
            violations.append(f"{relative} does not import {protocol_module}")
        forbidden = (
            "huginn.elt.silver.repositories.source_context_repository",
            "huginn.elt.silver.repositories.source_currentness_repository",
            "huginn.elt.silver.infrastructure",
            "huginn.elt.silver.presentation",
        )
        if any(module.startswith(forbidden) for module in modules):
            violations.append(f"{relative} imports a concrete outer-layer module")
    assert not violations, (
        "Silver services must depend on repository protocols: " + "; ".join(violations)
    )
