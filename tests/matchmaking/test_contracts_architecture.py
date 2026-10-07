import ast
from pathlib import Path
from types import TracebackType
from typing import get_type_hints
from uuid import uuid4

from huginn.matchmaking.application.protocols.clock import Clock
from huginn.matchmaking.application.read_models.company_candidate import (
    CompanyCandidate,
)
from huginn.matchmaking.application.read_models.strategy_configuration import (
    StrategyConfiguration,
)
from huginn.matchmaking.application.read_models.user_availability import (
    UserAvailability,
)
from huginn.matchmaking.domain.value_objects.compiled_criteria import CompiledCriteria
from huginn.matchmaking.persistence.repositories.protocols.candidates import (
    CandidateRepository,
)
from huginn.matchmaking.persistence.repositories.protocols.configuration import (
    ConfigurationRepository,
)
from huginn.matchmaking.persistence.repositories.protocols.matches import (
    MatchRepository,
)
from huginn.matchmaking.persistence.unit_of_work.protocol import MatchmakingUnitOfWork

ROOT = Path(__file__).parents[2] / "src/huginn/matchmaking"


def test_expected_layered_contract_files_exist():
    expected = (
        "application/requests/matchmaking_request.py",
        "application/requests/batch_matchmaking_request.py",
        "application/responses/matchmaking_response.py",
        "application/responses/batch_matchmaking_response.py",
        "application/responses/skipped_strategy.py",
        "application/responses/user_failure.py",
        "application/read_models/strategy_configuration.py",
        "application/read_models/company_candidate.py",
        "application/read_models/user_availability.py",
        "application/protocols/clock.py",
        "application/errors/execution.py",
        "domain/entities/match.py",
        "domain/value_objects/signal_window.py",
        "domain/value_objects/compiled_criteria.py",
        "domain/services/icp_evaluator.py",
        "domain/types/json_value.py",
        "domain/constants/targeting.py",
        "domain/errors/criteria.py",
        "persistence/repositories/protocols/configuration.py",
        "persistence/repositories/protocols/candidates.py",
        "persistence/repositories/protocols/matches.py",
        "persistence/row_models/json_value.py",
        "persistence/unit_of_work/protocol.py",
        "persistence/errors/database.py",
    )

    assert all((ROOT / path).is_file() for path in expected)


def test_domain_has_no_application_persistence_or_presentation_imports():
    for source in (ROOT / "domain").rglob("*.py"):
        tree = ast.parse(source.read_text())
        imports = [
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        ] + [
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        ]
        assert not any(
            name.startswith("huginn.matchmaking.application")
            or name.startswith("huginn.matchmaking.persistence")
            or name.startswith("huginn.matchmaking.presentation")
            or name.startswith("huginn.management")
            or name.startswith("huginn.elt")
            for name in imports
        ), source


def test_read_models_are_frozen_and_preserve_raw_criteria_shapes():
    from dataclasses import FrozenInstanceError

    ids = [uuid4() for _ in range(4)]
    config = StrategyConfiguration(*ids[:3], "Strategy", ids[3], None, (), (), ())
    candidate = CompanyCandidate(uuid4())

    assert config.industries is None
    assert candidate.company_id
    assert get_type_hints(StrategyConfiguration)["industries"] is not object
    try:
        config.name = "changed"
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError("read models must be immutable")


def test_repository_boundaries_use_the_declared_projection_and_entity_types():
    candidate_return = get_type_hints(CandidateRepository.find_candidates)["return"]
    config_availability = get_type_hints(ConfigurationRepository.user_availability)[
        "return"
    ]
    match_insert = get_type_hints(MatchRepository.insert_if_absent)["return"]
    uow_exit = get_type_hints(MatchmakingUnitOfWork.__exit__)
    clock_now = get_type_hints(Clock.now)["return"]

    assert candidate_return == tuple[CompanyCandidate, ...]
    assert config_availability is UserAvailability
    assert "Match" in str(match_insert)
    assert uow_exit["traceback"] == TracebackType | None
    assert "datetime" in str(clock_now)
    assert (
        get_type_hints(CandidateRepository.find_candidates)["criteria"]
        is CompiledCriteria
    )
