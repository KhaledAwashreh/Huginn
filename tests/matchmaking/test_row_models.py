from datetime import UTC, datetime
from types import MappingProxyType
from uuid import uuid4

import pytest

from huginn.matchmaking.persistence.errors.database import DataIntegrityError
from huginn.matchmaking.persistence.row_models.json_value import freeze_json_value
from huginn.matchmaking.persistence.row_models.match import MatchRow
from huginn.matchmaking.persistence.row_models.strategy_configuration import (
    StrategyConfigurationRow,
)


def test_freeze_preserves_malformed_shapes_and_is_deeply_immutable():
    source = [{"unexpected": [1, None, True]}]
    frozen = freeze_json_value(source)
    source[0]["unexpected"].append(2)
    assert frozen[0]["unexpected"] == (1, None, True)
    assert isinstance(frozen[0], MappingProxyType)
    with pytest.raises(TypeError):
        frozen[0]["new"] = 1
    assert freeze_json_value(None) is None
    assert freeze_json_value({"bad_outer": False}) == {"bad_outer": False}


@pytest.mark.parametrize("value", [object(), {1: "bad key"}, {"uuid": uuid4()}, {1, 2}])
def test_non_json_driver_values_fail(value):
    with pytest.raises(DataIntegrityError):
        freeze_json_value(value)


def test_strategy_identifiers_and_join_sentinels_are_strict_but_json_is_not():
    ids = [uuid4() for _ in range(6)]
    row = StrategyConfigurationRow(
        ids[0], ids[1], "Target", ids[2], ids[3], ids[2], ids[3], None, {}, [], True
    )
    projection = row.to_read_model()
    assert projection.industries is None
    assert projection.company_sizes == {}
    with pytest.raises(DataIntegrityError):
        StrategyConfigurationRow(
            str(ids[0]),
            ids[1],
            "Target",
            ids[2],
            ids[3],
            ids[4],
            ids[5],
            [],
            [],
            [],
            [],
        )
    with pytest.raises(DataIntegrityError):
        StrategyConfigurationRow(
            ids[0], ids[1], "Target", ids[2], ids[3], None, ids[5], [], [], [], []
        ).to_read_model()


@pytest.mark.parametrize("status", ["unknown", True])
def test_match_row_rejects_unknown_status(status):
    now = datetime.now(UTC)
    with pytest.raises(DataIntegrityError):
        MatchRow(uuid4(), uuid4(), uuid4(), status, None, now, now).to_domain()


def test_match_row_rejects_naive_timestamp():
    with pytest.raises(DataIntegrityError):
        MatchRow(
            uuid4(), uuid4(), uuid4(), "new", None, datetime.now(), datetime.now(UTC)
        ).to_domain()
