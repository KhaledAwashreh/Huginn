import ast
from pathlib import Path

ROOT = Path(__file__).parents[2]


def _imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }


def test_generation_service_uses_ports_and_shared_research_ranker():
    service = (
        ROOT / "src/huginn/management/application/services/recommendation_generation.py"
    )
    imports = _imports(service)
    assert not any("persistence.repositories" in value for value in imports)
    assert (
        "huginn.management.application.protocols.recommendation_generation" in imports
    )
    assert "huginn.matchmaking.application.services.research_ranking_service" in imports


def test_generation_query_owns_the_single_current_evidence_sql_implementation():
    query = (
        ROOT
        / "src/huginn/management/persistence/repositories/recommendation_generation.py"
    )
    legacy = ROOT / "src/huginn/management/persistence/repositories/recommendations.py"
    assert "gold.current_source_evidence" in query.read_text(encoding="utf-8")
    assert not legacy.exists(), (
        "The obsolete batch repository must be retired without a facade"
    )
    assert "set_config('statement_timeout','15000',true)" in query.read_text(
        encoding="utf-8"
    )
