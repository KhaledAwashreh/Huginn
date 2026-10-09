import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTROL = ROOT / "src" / "huginn" / "pipeline_control"


def test_domain_imports_do_not_cross_into_application_or_adapters():
    for path in (CONTROL / "domain").rglob("*.py"):
        tree = ast.parse(path.read_text())
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        imported.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        assert not any(
            module.startswith("huginn.pipeline_control.application")
            or module.startswith("huginn.pipeline_control.persistence")
            or module.startswith("huginn.pipeline_control.presentation")
            for module in imported
        ), path


def test_application_request_and_projection_dataclasses_are_frozen():
    for boundary in ("requests", "responses", "read_models"):
        for path in (CONTROL / "application" / boundary).glob("*.py"):
            tree = ast.parse(path.read_text())
            for node in tree.body:
                if not isinstance(node, ast.ClassDef):
                    continue
                decorators = [
                    decorator.func if isinstance(decorator, ast.Call) else decorator
                    for decorator in node.decorator_list
                ]
                if not any(
                    isinstance(decorator, ast.Name) and decorator.id == "dataclass"
                    for decorator in decorators
                ):
                    continue
                dataclass_call = next(
                    decorator
                    for decorator in node.decorator_list
                    if isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Name)
                    and decorator.func.id == "dataclass"
                )
                assert any(
                    keyword.arg == "frozen"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is True
                    for keyword in dataclass_call.keywords
                ), f"{path}:{node.name} must be frozen"
