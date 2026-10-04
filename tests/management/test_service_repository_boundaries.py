import ast
from pathlib import Path

ROOT = Path(__file__).parents[2] / "src/huginn/management"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_services_and_repositories_do_not_import_http_or_pydantic_schemas():
    for package in (ROOT / "application/services", ROOT / "persistence/repositories"):
        assert package.is_dir()
        for path in package.rglob("*.py"):
            imports = _imports(path)
            service_concrete_repository = package.name == "services" and any(
                name == "huginn.management.persistence.repositories"
                or name.startswith("huginn.management.persistence.repositories.")
                for name in imports
            )
            service_transport_import = package.name == "services" and any(
                name == "pydantic"
                or name.startswith("pydantic.")
                or name == "huginn.management.presentation.api.primitives"
                or name.startswith("huginn.management.presentation.api.primitives.")
                for name in imports
            )
            assert (
                not any(
                    name.startswith("huginn.management.presentation.")
                    or name in {"fastapi", "starlette"}
                    or name.startswith(("fastapi.", "starlette."))
                    for name in imports
                )
                and not service_concrete_repository
                and not service_transport_import
            ), path
