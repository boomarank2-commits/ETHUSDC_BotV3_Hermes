"""Task-25 tests for daily outer MTM and separate time aggregations."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import importlib.util
import json
from pathlib import Path

import pytest

from ethusdc_bot.protocol_v3 import outer_mtm_ledger as ledger
from ethusdc_bot.protocol_v3 import outer_mtm_ledger_api, outer_origins, runtime_state

REPO_ROOT = Path(__file__).resolve().parents[2]
_TASK23_PATH = Path(__file__).with_name("test_protocol_v3_outer_origins.py")
_SPEC = importlib.util.spec_from_file_location(
    "protocol_v3_task25_support", _TASK23_PATH
)
assert _SPEC is not None and _SPEC.loader is not None
task23 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(task23)


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _, plan, requests = task23.state.__wrapped__(tmp_path, monkeypatch)
    process = outer_origins.orchestrate_outer_origins(plan, requests)
    return plan, process


def _inputs(plan, process, *, gain_day=None, include_trade=False):
    selected = process.to_dict()["origins"]
    equity = 0
    values = []
    for origin, selection in zip(plan.origins, selected, strict=True):
        opening = equity
        bundle = selection["frozen_candidate_bundle"]["bundle_sha256"]
        rows = []
        for day in origin.iter_test_days():
            net = 1 if day == gain_day else 0
            equity += net
            rows.append(
                {
                    "day_utc": day.isoformat(),
                    "net_mtm_usdc": str(net),
                    "closing_equity_usdc": str(equity),
                }
            )
        trades = []
        events = []
        if include_trade and origin.origin_index == 1:
            at = datetime.combine(origin.test_start_inclusive, datetime.min.time(), UTC)
            trades = [
                {
                    "trade_id": "trade_001",
                    "candidate_bundle_sha256": bundle,
                    "entry_time_utc": at.isoformat().replace("+00:00", "Z"),
                    "exit_time_utc": at.replace(hour=1)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "gross_usdc": "1.3",
                    "fees_usdc": "0.2",
                    "slippage_usdc": "0.1",
                    "net_usdc": "1",
                    "terminal_liquidation": False,
                }
            ]
            events = [
                {
                    "event_id": "event_001",
                    "trade_id": "trade_001",
                    "execution_time_utc": at.isoformat().replace("+00:00", "Z"),
                    "kind": "fee",
                    "amount_usdc": "0.2",
                },
                {
                    "event_id": "event_002",
                    "trade_id": "trade_001",
                    "execution_time_utc": at.replace(hour=1)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "kind": "slippage",
                    "amount_usdc": "0.1",
                },
            ]
        rotation = runtime_state.build_outer_rotation_state(
            origin, new_candidate_bundle_sha256=bundle
        )
        values.append(
            ledger.OriginLedgerInput(
                origin.origin_index,
                selection["origin_sha256"],
                bundle,
                rotation,
                str(opening),
                None,
                rows,
                trades,
                events,
            )
        )
    return values


def test_contract_api_and_pipeline_binding_are_exact() -> None:
    contract = ledger.load_outer_mtm_ledger_contract(REPO_ROOT)
    assert contract["contract_version"] == ledger.CONTRACT_VERSION
    assert (
        contract["attribution_policy"][
            "mtm_and_closed_trade_pnl_are_never_added_together"
        ]
        is True
    )
    assert outer_mtm_ledger_api.__all__ == ledger.__all__
    pipeline = json.loads(
        (REPO_ROOT / "configs/protocol_v3_pipeline_contract.json").read_text()
    )
    assert ledger.CONTRACT_VERSION in pipeline["component_contracts"]["ranking"]
    for path in (
        "configs/protocol_v3_outer_mtm_ledger_contract.json",
        "src/ethusdc_bot/protocol_v3/outer_mtm_ledger.py",
        "src/ethusdc_bot/protocol_v3/outer_mtm_ledger_api.py",
    ):
        assert path in pipeline["source_bindings"]["ranking"]


def test_zero_process_keeps_all_365_days_12_deployments_13_months_and_5_quarters(
    state,
) -> None:
    plan, process = state
    result = ledger.build_outer_mtm_ledger(plan, process, _inputs(plan, process))
    payload = result.to_dict()
    assert len(payload["daily_mtm"]) == 365
    assert all(row["net_mtm_usdc"] == "0" for row in payload["daily_mtm"])
    assert len(payload["deployment_intervals"]) == 12
    assert len(payload["calendar_months"]) == 13
    assert len(payload["calendar_quarters"]) == 5
    assert (
        payload["totals"]["pnl_combination_policy"]
        == "mtm_primary_closed_trade_diagnostic_never_added"
    )
    assert (
        ledger.validate_outer_mtm_ledger(
            payload, boundary_plan=plan, outer_process=process
        )
        == result
    )


def test_trade_net_is_mtm_total_but_remains_a_separate_diagnostic(state) -> None:
    plan, process = state
    gain_day = plan.origins[0].test_start_inclusive
    result = ledger.build_outer_mtm_ledger(
        plan, process, _inputs(plan, process, gain_day=gain_day, include_trade=True)
    ).to_dict()
    assert result["totals"]["net_mtm_usdc"] == "1"
    assert result["totals"]["closed_trade_net_usdc_diagnostic"] == "1"
    assert result["totals"]["trade_count"] == 1
    assert sum(row["exit_trade_count"] for row in result["calendar_months"]) == 1
    assert sum(row["exit_trade_count"] for row in result["calendar_quarters"]) == 1


def test_missing_zero_day_and_broken_equity_delta_fail_closed(state) -> None:
    plan, process = state
    inputs = _inputs(plan, process)
    missing = list(inputs)
    missing[0] = ledger.OriginLedgerInput(
        inputs[0].origin_index,
        inputs[0].origin_selection_sha256,
        inputs[0].candidate_bundle_sha256,
        inputs[0].rotation_state,
        inputs[0].opening_equity_usdc,
        inputs[0].ending_open_position_bundle_sha256,
        list(inputs[0].daily_mtm)[1:],
        (),
        (),
    )
    with pytest.raises(ledger.OuterMtmLedgerError, match="every UTC day"):
        ledger.build_outer_mtm_ledger(plan, process, missing)
    broken = deepcopy(list(inputs[0].daily_mtm))
    broken[0]["closing_equity_usdc"] = "1"
    changed = list(inputs)
    changed[0] = ledger.OriginLedgerInput(
        inputs[0].origin_index,
        inputs[0].origin_selection_sha256,
        inputs[0].candidate_bundle_sha256,
        inputs[0].rotation_state,
        inputs[0].opening_equity_usdc,
        inputs[0].ending_open_position_bundle_sha256,
        broken,
        (),
        (),
    )
    with pytest.raises(ledger.OuterMtmLedgerError, match="closing-equity delta"):
        ledger.build_outer_mtm_ledger(plan, process, changed)


def test_wrong_rotation_bundle_and_wrong_exit_origin_fail_closed(state) -> None:
    plan, process = state
    inputs = _inputs(plan, process)
    wrong_rotation = runtime_state.build_outer_rotation_state(
        plan.origins[0], new_candidate_bundle_sha256="9" * 64
    )
    changed = list(inputs)
    changed[0] = ledger.OriginLedgerInput(
        inputs[0].origin_index,
        inputs[0].origin_selection_sha256,
        inputs[0].candidate_bundle_sha256,
        wrong_rotation,
        inputs[0].opening_equity_usdc,
        inputs[0].ending_open_position_bundle_sha256,
        inputs[0].daily_mtm,
        (),
        (),
    )
    with pytest.raises(ledger.OuterMtmLedgerError, match="rotation state candidate"):
        ledger.build_outer_mtm_ledger(plan, process, changed)

    hidden_open = list(inputs)
    hidden_open[-1] = ledger.OriginLedgerInput(
        inputs[-1].origin_index,
        inputs[-1].origin_selection_sha256,
        inputs[-1].candidate_bundle_sha256,
        inputs[-1].rotation_state,
        inputs[-1].opening_equity_usdc,
        "8" * 64,
        inputs[-1].daily_mtm,
        (),
        (),
    )
    with pytest.raises(ledger.OuterMtmLedgerError, match="must end flat"):
        ledger.build_outer_mtm_ledger(plan, process, hidden_open)

    trade_inputs = _inputs(
        plan, process, gain_day=plan.origins[0].test_start_inclusive, include_trade=True
    )
    bad_trade = deepcopy(list(trade_inputs[0].closed_trades))
    bad_trade[0]["exit_time_utc"] = (
        plan.origins[1].valid_from.isoformat().replace("+00:00", "Z")
    )
    trade_inputs[0] = ledger.OriginLedgerInput(
        trade_inputs[0].origin_index,
        trade_inputs[0].origin_selection_sha256,
        trade_inputs[0].candidate_bundle_sha256,
        trade_inputs[0].rotation_state,
        trade_inputs[0].opening_equity_usdc,
        trade_inputs[0].ending_open_position_bundle_sha256,
        trade_inputs[0].daily_mtm,
        bad_trade,
        trade_inputs[0].friction_events,
    )
    with pytest.raises(ledger.OuterMtmLedgerError, match="UTC exit origin"):
        ledger.build_outer_mtm_ledger(plan, process, trade_inputs)


def test_trade_friction_and_mtm_total_mismatch_cannot_be_hidden(state) -> None:
    plan, process = state
    inputs = _inputs(
        plan, process, gain_day=plan.origins[0].test_start_inclusive, include_trade=True
    )
    bad_events = deepcopy(list(inputs[0].friction_events))
    bad_events[0]["amount_usdc"] = "0.1"
    changed = list(inputs)
    changed[0] = ledger.OriginLedgerInput(
        inputs[0].origin_index,
        inputs[0].origin_selection_sha256,
        inputs[0].candidate_bundle_sha256,
        inputs[0].rotation_state,
        inputs[0].opening_equity_usdc,
        inputs[0].ending_open_position_bundle_sha256,
        inputs[0].daily_mtm,
        inputs[0].closed_trades,
        bad_events,
    )
    with pytest.raises(ledger.OuterMtmLedgerError, match="friction totals"):
        ledger.build_outer_mtm_ledger(plan, process, changed)

    no_gain = _inputs(plan, process, include_trade=True)
    with pytest.raises(ledger.OuterMtmLedgerError, match="MTM total"):
        ledger.build_outer_mtm_ledger(plan, process, no_gain)
