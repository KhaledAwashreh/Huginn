"""Pure Silver code cannot acquire IO through an intermediate local import."""

import ast
from pathlib import Path

ROOT = Path(__file__).parents[4]
SOURCE = ROOT / "src"
SILVER = SOURCE / "huginn" / "elt" / "silver"
IO_MODULES = {"requests", "httpx", "psycopg", "socket", "subprocess"}


def _dependencies(module: str) -> set[str]:
    path = SOURCE.joinpath(*module.split("."))
    source = path.with_suffix(".py")
    if not source.is_file():
        source = path / "__init__.py"
    if not source.is_file():
        return set()
    imports = set()
    for node in ast.walk(ast.parse(source.read_text())):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def _find_io(module: str, seen: set[str]) -> list[str]:
    if module in seen:
        return []
    seen.add(module)
    violations = []
    for imported in _dependencies(module):
        if imported.split(".")[0] in IO_MODULES:
            violations.append(f"{module} -> {imported}")
        elif imported.startswith("huginn."):
            violations.extend(
                f"{module} -> {edge}" for edge in _find_io(imported, seen)
            )
    return violations


def test_pure_silver_roles_do_not_load_network_or_database_clients_transitively():
    violations = []
    for role in ("models", "policies", "normalizers", "types", "constants"):
        for path in (SILVER / role).glob("*.py"):
            relative = path.relative_to(SOURCE).with_suffix("")
            violations.extend(_find_io(".".join(relative.parts), set()))
    assert not violations, "Pure modules load IO dependencies:\n" + "\n".join(
        violations
    )
