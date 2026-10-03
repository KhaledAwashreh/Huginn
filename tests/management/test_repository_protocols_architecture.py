import ast
import importlib
import inspect
from pathlib import Path

PROTOCOL_MODULES = (
    "account",
    "user",
    "professional_profile",
    "session",
    "service_offering",
    "ideal_client_profile",
    "discovery_strategy",
    "common",
)


def _protocols():
    for module_name in PROTOCOL_MODULES:
        module = importlib.import_module(
            f"huginn.management.repositories.protocols.{module_name}"
        )
        yield from (
            value
            for value in vars(module).values()
            if getattr(value, "_is_protocol", False)
            and getattr(value, "__module__", None) == module.__name__
        )


def test_protocol_modules_do_not_import_infrastructure_or_transport():
    package = Path(__file__).parents[2] / "src/huginn/management/repositories/protocols"
    forbidden_roots = {
        "fastapi",
        "starlette",
        "psycopg",
        "requests",
        "responses",
        "flask",
        "werkzeug",
    }

    for source_path in package.glob("*.py"):
        syntax = ast.parse(source_path.read_text())
        imported = {
            alias.name.split(".")[0]
            for node in ast.walk(syntax)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            (node.module or "").split(".")[0]
            for node in ast.walk(syntax)
            if isinstance(node, ast.ImportFrom)
        }
        assert not forbidden_roots.intersection(imported), source_path


def test_obsolete_repository_port_compatibility_module_is_removed():
    root = Path(__file__).parents[2] / "src/huginn/management"
    assert not (root / "repository_ports.py").exists()


def test_protocols_do_not_annotate_transport_or_database_values():
    forbidden_fragments = (
        "fastapi",
        "starlette",
        "psycopg",
        "request",
        "response",
        "pydantic",
    )

    for protocol in _protocols():
        for member in vars(protocol).values():
            if not inspect.isfunction(member):
                continue
            annotation_text = str(inspect.get_annotations(member)).lower()
            assert not any(
                fragment in annotation_text for fragment in forbidden_fragments
            )
