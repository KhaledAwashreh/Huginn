import ast
from pathlib import Path

ROOT = Path(__file__).parents[2]
DOMAIN_FILES = tuple((ROOT / "src/huginn/management/domain").rglob("*.py")) + tuple(
    (ROOT / "src/huginn/matchmaking/domain").rglob("*.py")
)
PORT_FILES = tuple((ROOT / "src/huginn/management/persistence/contracts").rglob("*.py"))


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    return {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }


def test_domain_modules_do_not_depend_on_io_application_or_presentation():
    forbidden_prefixes = (
        "psycopg",
        "huginn.management.application",
        "huginn.management.persistence",
        "huginn.management.presentation",
        "huginn.matchmaking.application",
        "huginn.matchmaking.persistence",
        "huginn.matchmaking.presentation",
    )
    for path in DOMAIN_FILES:
        assert not any(
            imported == prefix or imported.startswith(prefix + ".")
            for imported in _imports(path)
            for prefix in forbidden_prefixes
        ), path


def test_repository_contracts_do_not_import_adapters_or_presentation():
    forbidden_prefixes = (
        "huginn.management.application",
        "huginn.management.presentation",
        "huginn.management.persistence.repositories",
    )
    for path in PORT_FILES:
        assert not any(
            imported == prefix or imported.startswith(prefix + ".")
            for imported in _imports(path)
            for prefix in forbidden_prefixes
        ), path


def test_application_modules_do_not_import_concrete_io_or_presentation():
    forbidden_prefixes = (
        "huginn.management.persistence.database",
        "huginn.management.persistence.repositories",
        "huginn.management.persistence.queries",
        "huginn.management.presentation",
        "huginn.management.delivery",
        "psycopg",
        "smtplib",
        "httpx",
        "requests",
        "urllib.request",
    )
    for path in (ROOT / "src/huginn/management/application").rglob("*.py"):
        assert not any(
            imported == prefix or imported.startswith(prefix + ".")
            for imported in _imports(path)
            for prefix in forbidden_prefixes
        ), path


def test_each_new_domain_model_module_defines_at_most_one_public_class():
    model_directories = (
        ROOT / "src/huginn/management/domain/entities",
        ROOT / "src/huginn/management/domain/value_objects",
        ROOT / "src/huginn/matchmaking/domain/value_objects",
    )
    for directory in model_directories:
        for path in directory.glob("*.py"):
            if path.name.startswith("_"):
                continue
            tree = ast.parse(path.read_text())
            public_classes = [
                node.name
                for node in tree.body
                if isinstance(node, ast.ClassDef) and not node.name.startswith("_")
            ]
            if path.name in {
                "assessment_revision.py",
                "business_changes.py",
                "new_business.py",
                "accepted_offer_cadence.py",
                "weekly_digest_content.py",
                "weekly_digest_delivery.py",
                "weekly_digest_member.py",
                "command_receipt.py",
                "offer_cycle.py",
                "prospect.py",
                "prospect_activity.py",
                "prospect_origin.py",
                "recommendation.py",
                "recommendation_assessment_feedback.py",
                "suppression_block.py",
                "activity_kind.py",
                "command_identity.py",
                "discovery_decision.py",
                "discovery_resolution.py",
                "json_snapshot.py",
                "later_pause.py",
                "offer_cycle_status.py",
                "origin_append_result.py",
                "pause_choice.py",
                "prospect_stage.py",
                "recommendation_status.py",
                "rejection_reversal.py",
                "strategy_assessment_snapshot.py",
                "suppression_kind.py",
                "business_company_state.py",
                "company_fit_assessment.py",
                "recommendation_eligibility.py",
            }:
                assert len(public_classes) == 1, (path, public_classes)
