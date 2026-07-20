"""Task-29 order-free controller and forward-ledger regressions."""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from ethusdc_bot.backtest.context_features import CONTEXT_POLICY_VERSION, ContextDecision
from ethusdc_bot.backtest.data_loader import AlignedMarketCandles, Candle
from ethusdc_bot.protocol_v3 import pipeline, research_challenger

REPO_ROOT = Path(__file__).resolve().parents[2]
_TASK28_PATH = Path(__file__).with_name("test_protocol_v3_current_refit.py")
_SPEC28 = importlib.util.spec_from_file_location(
    "protocol_v3_task29_task28_support", _TASK28_PATH
)
assert _SPEC28 is not None and _SPEC28.loader is not None
task28 = importlib.util.module_from_spec(_SPEC28)
_SPEC28.loader.exec_module(task28)


def _series(start_ms: int, values: tuple[float, ...]) -> tuple[Candle, ...]:
    return tuple(
        Candle(
            open_time=start_ms + index * 60_000,
            open=value,
            high=value + 0.5,
            low=value - 0.5,
            close=value,
            volume=10.0,
        )
        for index, value in enumerate(values)
    )


def _binding(start_ms: int, count: int = 4):
    values = tuple(100.0 + index * 0.1 for index in range(count))
    context = AlignedMarketCandles(
        ethusdc=_series(start_ms, values),
        btcusdc=_series(start_ms, values),
        ethbtc=_series(start_ms, tuple(1.0 + index * 0.001 for index in range(count))),
    )
    return SimpleNamespace(
        context=context,
        common_watermark_open_time_ms=context.ethusdc[-1].open_time,
        context_identity_sha256="c" * 64,
    )


def _allow_context(_binding, index: int, *, decision_time_ms: int) -> ContextDecision:
    candle = _binding.context.ethusdc[index]
    assert decision_time_ms == candle.open_time + 59_999
    return ContextDecision(
        allowed=True,
        reason="context_confirmed",
        index=index,
        open_time=candle.open_time,
        policy_version=CONTEXT_POLICY_VERSION,
        btc_trend_bps=1.0,
        btc_volatility_bps=1.0,
        ethbtc_trend_bps=1.0,
    )


def _generation():
    return pipeline.build_pipeline_generation(REPO_ROOT)


@pytest.fixture
def task28_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    return task28.state.__wrapped__(tmp_path, monkeypatch)[-1]


def test_cash_controller_is_manual_order_free_and_refresh_idempotent(
    task28_report, monkeypatch: pytest.MonkeyPatch
) -> None:
    valid_from = datetime(2026, 7, 9, tzinfo=UTC)
    generation = _generation()
    state = research_challenger.start_research_challenger(
        task28_report,
        started_at_utc=valid_from,
        current_pipeline_generation=generation,
    )
    assert state.to_dict()["mode"] == "CASH"

    binding = _binding(int(valid_from.timestamp() * 1000))
    monkeypatch.setattr(
        research_challenger, "validate_context_parity_binding", lambda value: None
    )
    monkeypatch.setattr(
        research_challenger, "evaluate_closed_bar_context", _allow_context
    )
    observed = datetime.fromtimestamp(
        (binding.common_watermark_open_time_ms + 59_999) / 1000,
        tz=UTC,
    )

    first = research_challenger.advance_research_challenger(
        state,
        binding,
        observed_at_utc=observed,
        current_pipeline_generation=generation,
    )
    payload = first.state.to_dict()
    assert len(first.new_records) == 4
    assert payload["forward_ledger"]["record_count"] == 4
    assert payload["forward_ledger"]["head_sha256"] == first.new_records[-1][
        "record_sha256"
    ]
    assert all(record["mode"] == "CASH" for record in first.new_records)
    assert all(record["entry_allowed"] is False for record in first.new_records)
    assert all(record["orders_created"] == 0 for record in first.new_records)
    assert all(record["private_api_calls"] == 0 for record in first.new_records)

    repeated = research_challenger.advance_research_challenger(
        first.state,
        binding,
        observed_at_utc=observed,
        current_pipeline_generation=generation,
    )
    assert repeated.new_records == ()
    assert repeated.state == first.state


def test_manual_start_never_backfills_earlier_forward_minutes(
    task28_report, monkeypatch: pytest.MonkeyPatch
) -> None:
    valid_from = datetime(2026, 7, 9, tzinfo=UTC)
    started = valid_from + timedelta(minutes=2, seconds=15)
    generation = _generation()
    state = research_challenger.start_research_challenger(
        task28_report,
        started_at_utc=started,
        current_pipeline_generation=generation,
    )
    activation = int((valid_from + timedelta(minutes=3)).timestamp() * 1000)
    binding = _binding(int(valid_from.timestamp() * 1000), count=6)
    monkeypatch.setattr(
        research_challenger, "validate_context_parity_binding", lambda value: None
    )
    monkeypatch.setattr(
        research_challenger, "evaluate_closed_bar_context", _allow_context
    )
    observed = datetime.fromtimestamp(
        (binding.common_watermark_open_time_ms + 59_999) / 1000,
        tz=UTC,
    )

    advanced = research_challenger.advance_research_challenger(
        state,
        binding,
        observed_at_utc=observed,
        current_pipeline_generation=generation,
    )
    assert [row["open_time_ms"] for row in advanced.new_records] == [
        activation,
        activation + 60_000,
        activation + 120_000,
    ]


def test_forward_ledger_side_effect_tampering_fails_closed(
    task28_report, monkeypatch: pytest.MonkeyPatch
) -> None:
    valid_from = datetime(2026, 7, 9, tzinfo=UTC)
    generation = _generation()
    state = research_challenger.start_research_challenger(
        task28_report,
        started_at_utc=valid_from,
        current_pipeline_generation=generation,
    )
    binding = _binding(int(valid_from.timestamp() * 1000), count=1)
    monkeypatch.setattr(
        research_challenger, "validate_context_parity_binding", lambda value: None
    )
    monkeypatch.setattr(
        research_challenger, "evaluate_closed_bar_context", _allow_context
    )
    observed = datetime.fromtimestamp(
        (binding.common_watermark_open_time_ms + 59_999) / 1000,
        tz=UTC,
    )
    advanced = research_challenger.advance_research_challenger(
        state,
        binding,
        observed_at_utc=observed,
        current_pipeline_generation=generation,
    )

    changed = deepcopy(advanced.state.to_dict())
    changed["forward_ledger"]["records"][0]["orders_created"] = 1
    record = changed["forward_ledger"]["records"][0]
    record_basis = dict(record)
    record_basis.pop("record_sha256")
    record["record_sha256"] = research_challenger._digest(record_basis)
    changed["forward_ledger"]["head_sha256"] = record["record_sha256"]
    basis = dict(changed)
    basis.pop("state_sha256")
    changed["state_sha256"] = research_challenger._digest(basis)

    with pytest.raises(research_challenger.ResearchChallengerError, match="side effects"):
        research_challenger.validate_research_challenger_state(changed)
