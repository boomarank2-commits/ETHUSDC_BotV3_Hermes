from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from ethusdc_bot.protocol_v3.production_runtime import (
    ProductionRuntimeError,
    build_task33_runtime_inputs,
    load_production_runtime_inputs,
    validate_production_runtime_inputs,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_frozen_production_inputs_match_audited_warmup_and_specialist_maximum() -> None:
    root = load_production_runtime_inputs(REPO_ROOT)

    assert [row["market"] for row in root["active_lookbacks"]] == [
        "BTCUSDC",
        "ETHBTC",
        "ETHUSDC",
    ]
    assert max(row["duration_seconds"] for row in root["active_lookbacks"]) == 1_728_000
    assert root["horizon_policy"] == {
        "max_label_horizon_minutes": 10_080,
        "max_holding_period_minutes": 10_080,
        "pending_entry_latency_minutes": 2,
        "execution_bar_minutes": 1,
    }


def test_task33_projection_keeps_adapter_fail_closed() -> None:
    inputs = build_task33_runtime_inputs(
        REPO_ROOT, production_outer_origin_adapter=False
    )

    assert inputs["active_lookbacks"]
    assert inputs["horizon_policy"]["max_holding_period_minutes"] == 10_080
    assert inputs["production_outer_origin_adapter"] is False


@pytest.mark.parametrize(
    "mutate",
    [
        lambda root: root["active_lookbacks"][0].update(bars=167),
        lambda root: root["horizon_policy"].update(max_holding_period_minutes=720),
        lambda root: root["safety"].update(orders="allowed"),
    ],
)
def test_runtime_contract_rejects_rehashed_or_shortened_claims(mutate) -> None:
    root = deepcopy(load_production_runtime_inputs(REPO_ROOT))
    mutate(root)

    with pytest.raises(ProductionRuntimeError):
        validate_production_runtime_inputs(root)
