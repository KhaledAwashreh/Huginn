"""Guard Gold assessment package boundaries against flattening."""

import ast
from pathlib import Path

GOLD = Path(__file__).resolve().parents[4] / "src/huginn/elt/gold"


def imports(module: str) -> set[str]:
    tree = ast.parse((GOLD / module).read_text())
    return {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }


def test_assessment_components_live_in_responsibility_packages() -> None:
    assert not (GOLD / "attribute_promotion").exists()
    for path in (
        "models/company_attributes.py",
        "models/source_fact.py",
        "models/field_proposal.py",
        "models/assessment_snapshot.py",
        "models/assessment_result.py",
        "models/attribute_value.py",
        "policies/attribute_assessment.py",
        "policies/attribute_comparison.py",
        "policies/country_labels.py",
        "repositories/attribute_assessment_repository.py",
        "repositories/protocols/attribute_assessment_repository.py",
        "services/attribute_assessment.py",
        "presentation/cli/attribute_assessment.py",
        "presentation/serializers/attribute_assessment.py",
    ):
        assert (GOLD / path).is_file(), path


def test_dependencies_point_inward_and_models_and_policies_are_pure() -> None:
    pure_modules = [
        *(
            f"models/{name}"
            for name in (
                "company_attributes.py",
                "source_fact.py",
                "field_proposal.py",
                "assessment_snapshot.py",
                "assessment_result.py",
                "attribute_value.py",
            )
        ),
        "policies/attribute_assessment.py",
        "policies/attribute_comparison.py",
        "policies/country_labels.py",
    ]
    for module in pure_modules:
        deps = imports(module)
        assert not any(dep.startswith("psycopg") for dep in deps), module
        assert not any("presentation" in dep for dep in deps), module
    assert not any(
        "presentation" in dep for dep in imports("services/attribute_assessment.py")
    )
    assert not any(
        dep.startswith("psycopg")
        for dep in imports("repositories/protocols/attribute_assessment_repository.py")
    )
    repo_imports = imports("repositories/attribute_assessment_repository.py")
    assert any(
        "repositories.protocols.attribute_assessment_repository" in dep
        for dep in repo_imports
    )
    cli_imports = imports("presentation/cli/attribute_assessment.py")
    assert any("services.attribute_assessment" in dep for dep in cli_imports)
    assert any(
        "repositories.attribute_assessment_repository" in dep for dep in cli_imports
    )


def test_comparison_decisions_live_in_policy_not_service() -> None:
    service_tree = ast.parse((GOLD / "services/attribute_assessment.py").read_text())
    service_defs = {
        node.name
        for node in service_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert not service_defs.intersection(
        {"_normal", "_canonical", "_alias_criteria", "_missing", "_gates"}
    )
    assert (GOLD / "policies/attribute_comparison.py").is_file()
    policy_tree = ast.parse((GOLD / "policies/attribute_comparison.py").read_text())
    policy_defs = {
        node.name for node in policy_tree.body if isinstance(node, ast.FunctionDef)
    }
    assert {
        "canonical_country",
        "alias_criteria",
        "missing_fields",
        "gate_failures",
    } <= policy_defs
    service_imports = imports("services/attribute_assessment.py")
    assert any("policies.attribute_comparison" in dep for dep in service_imports)
