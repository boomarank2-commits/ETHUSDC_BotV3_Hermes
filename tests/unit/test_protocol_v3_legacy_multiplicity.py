from __future__ import annotations

import json
from pathlib import Path

import pytest

from ethusdc_bot.protocol_v3 import legacy_multiplicity_api
from ethusdc_bot.protocol_v3.legacy_multiplicity import (
    LEGACY_MULTIPLICITY_FLOOR,
    LegacyMultiplicityError,
    adjusted_n_raw,
    load_legacy_multiplicity_policy,
    validate_legacy_multiplicity_policy,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _inputs() -> tuple[dict, dict]:
    contract = json.loads(
        (REPO_ROOT / "configs/protocol_v3_legacy_multiplicity_contract.json").read_text()
    )
    source = json.loads(
        (REPO_ROOT / "configs/protocol_v3_historical_trial_lower_bound.json").read_text()
    )
    return contract, source


def test_real_legacy_inventory_becomes_multiplicity_only_floor() -> None:
    policy = load_legacy_multiplicity_policy(REPO_ROOT)

    assert policy.legacy_multiplicity_floor == LEGACY_MULTIPLICITY_FLOOR == 180
    assert adjusted_n_raw(policy, complete_native_trial_count=12) == 192
    payload = policy.to_dict()
    assert payload["legacy_identity_claimed"] is False
    assert payload["legacy_daily_series_used"] is False
    assert payload["legacy_pnl_used"] is False
    assert payload["legacy_rankings_or_gates_used"] is False
    assert legacy_multiplicity_api.__all__


@pytest.mark.parametrize(
    "mutation",
    [
        lambda contract, source: contract.update(legacy_multiplicity_floor=179),
        lambda contract, source: source.update(known_observed_evaluation_rows=179),
        lambda contract, source: source.update(identity_inventory_complete=True),
        lambda contract, source: source["sources"][0].update(
            observed_evaluation_rows=95
        ),
        lambda contract, source: contract["policy"].update(
            legacy_daily_series_used=True
        ),
    ],
)
def test_floor_tampering_or_legacy_data_reuse_fails_closed(mutation) -> None:
    contract, source = _inputs()
    mutation(contract, source)

    with pytest.raises(LegacyMultiplicityError):
        validate_legacy_multiplicity_policy(contract, source)


def test_floor_alone_never_satisfies_native_statistics() -> None:
    policy = load_legacy_multiplicity_policy(REPO_ROOT)

    with pytest.raises(LegacyMultiplicityError, match="native trials"):
        adjusted_n_raw(policy, complete_native_trial_count=0)
