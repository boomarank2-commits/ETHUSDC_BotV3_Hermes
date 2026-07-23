from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ethusdc_bot.protocol_v3 import production_outer_adapter as adapter
from ethusdc_bot.protocol_v3 import production_outer_adapter_api

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMIT = "a" * 40


def _snapshot() -> dict:
    return {
        "snapshot_sha256": "1" * 64,
        "boundary": {"process_end_exclusive": "2026-07-08"},
        "raw_interval": {
            "audited_full_day_start": "2026-07-05",
            "audited_full_day_end_inclusive": "2026-07-06",
        },
    }


def _exchange() -> dict:
    return {"snapshot_sha256": "2" * 64}


def _ledger() -> SimpleNamespace:
    status = SimpleNamespace(
        head_sha256="3" * 64,
        to_dict=lambda: {
            "known_observed_historical_evaluation_rows": 180,
            "historical_resolved_trial_count": 0,
            "historical_trial_count_is_lower_bound": False,
            "canonical_historical_import_present": True,
            "missing_daily_series_trial_ids": [],
        },
    )
    return SimpleNamespace(status=status)


@pytest.fixture
def planned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> adapter.ProductionOuterAdapterPlan:
    raw = tmp_path / "external_raw"
    raw.mkdir()
    monkeypatch.setattr(
        adapter, "validate_frozen_data_snapshot", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        adapter, "validate_exchange_info_snapshot", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(adapter, "_current_ledger", lambda value: value)
    monkeypatch.setattr(
        adapter,
        "_archive_inventory",
        lambda *args: {
            "markets": [],
            "common_required_day_count": 2,
            "inventory_sha256": "4" * 64,
        },
    )
    return adapter.build_production_outer_adapter_plan(
        repo_root=REPO_ROOT,
        raw_root=raw,
        data_snapshot=_snapshot(),
        exchange_info_snapshot=_exchange(),
        trial_ledger=_ledger(),
        code_commit=COMMIT,
    )


def test_contract_api_and_pipeline_binding_are_exact() -> None:
    contract = adapter.load_production_outer_adapter_contract(REPO_ROOT)
    assert contract["contract_version"] == adapter.CONTRACT_VERSION
    assert set(contract["required_task_contracts"]) == {
        str(index) for index in range(13, 28)
    }
    assert contract["readiness_policy"]["plan_alone_may_clear_task33"] is False
    assert production_outer_adapter_api.__all__ == adapter.__all__
    pipeline = json.loads(
        (REPO_ROOT / "configs/protocol_v3_pipeline_contract.json").read_text()
    )
    assert (
        adapter.CONTRACT_VERSION
        in pipeline["component_contracts"]["quality_gates"]
    )
    for path in (
        "configs/protocol_v3_production_outer_adapter_contract.json",
        "src/ethusdc_bot/protocol_v3/production_outer_adapter.py",
        "src/ethusdc_bot/protocol_v3/production_outer_adapter_api.py",
        "scripts/build_protocol_v3_production_outer_adapter_plan.py",
    ):
        assert path in pipeline["source_bindings"]["quality_gates"]


def test_plan_binds_all_tasks_origins_folds_budgets_and_safety(planned) -> None:
    payload = planned.to_dict()
    assert payload["state"] == adapter.PLAN_READY
    assert payload["execution_state"] == adapter.EXECUTOR_NOT_READY
    assert payload["origin_count"] == 12
    assert [row["origin_index"] for row in payload["origins"]] == list(
        range(1, 13)
    )
    assert all(
        row["fold_count"] == 6
        and row["validation_days"] == 360
        and row["max_cycles"] == 8
        for row in payload["origins"]
    )
    assert [row["task"] for row in payload["task_bindings"]] == list(
        range(13, 28)
    )
    assert payload["work_budget"] == {
        "outer_origins": 12,
        "max_cycles": 96,
        "max_generated_candidates": 3840,
        "max_tested_candidates": 1152,
        "max_walk_forward_candidates": 288,
        "max_finalists": 192,
    }
    assert payload["task33"] == {
        "plan_may_clear_blocker": False,
        "executor_attestation_required": True,
        "full_research_run_started": False,
    }
    assert payload["safety"]["orders"] == "locked"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("pipeline_generation_id", "f" * 64, "pipeline generation is stale"),
        ("origins", "not-a-list", "origins must be a list"),
        ("plan_sha256", "f" * 64, "digest mismatch"),
    ],
)
def test_tampered_plan_is_rejected(
    planned, field: str, value, message: str
) -> None:
    payload = planned.to_dict()
    payload[field] = value
    with pytest.raises(adapter.ProductionOuterAdapterError, match=message):
        adapter.validate_production_outer_adapter_plan(
            payload, repo_root=REPO_ROOT
        )


def test_task_binding_tamper_is_rejected(planned) -> None:
    payload = planned.to_dict()
    payload["task_bindings"][0]["source_sha256"] = "f" * 64
    with pytest.raises(
        adapter.ProductionOuterAdapterError, match="task bindings are stale"
    ):
        adapter.validate_production_outer_adapter_plan(
            payload, repo_root=REPO_ROOT
        )


def test_raw_root_must_not_overlap_repository(tmp_path: Path) -> None:
    with pytest.raises(
        adapter.ProductionOuterAdapterError, match="outside the repository"
    ):
        adapter._real_external_root(REPO_ROOT, REPO_ROOT)
    parent = REPO_ROOT.parent
    with pytest.raises(
        adapter.ProductionOuterAdapterError, match="outside the repository"
    ):
        adapter._real_external_root(parent, REPO_ROOT)


def _write_archive(root: Path, symbol: str, day: str) -> Path:
    folder = root / "raw" / "binance" / "spot" / symbol / "klines" / "1m"
    folder.mkdir(parents=True, exist_ok=True)
    archive = folder / f"{symbol}-1m-{day}.zip"
    archive.write_bytes(b"zip")
    archive.with_name(archive.name + ".CHECKSUM").write_text(
        "digest", encoding="utf-8"
    )
    return archive


def test_archive_inventory_requires_all_markets_days_and_checksums(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot()
    for symbol in adapter.MARKETS:
        _write_archive(tmp_path, symbol, "2026-07-05")
        _write_archive(tmp_path, symbol, "2026-07-06")
    inventory = adapter._archive_inventory(tmp_path, snapshot)
    assert inventory["common_required_day_count"] == 2
    assert [row["symbol"] for row in inventory["markets"]] == list(
        adapter.MARKETS
    )
    missing = (
        tmp_path
        / "raw"
        / "binance"
        / "spot"
        / "ETHBTC"
        / "klines"
        / "1m"
        / "ETHBTC-1m-2026-07-06.zip.CHECKSUM"
    )
    missing.unlink()
    with pytest.raises(
        adapter.ProductionOuterAdapterError, match="checksum is missing"
    ):
        adapter._archive_inventory(tmp_path, snapshot)


def test_contract_or_plan_cannot_overclaim_task33(
    planned, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = adapter.load_production_outer_adapter_contract(REPO_ROOT)
    unsafe = deepcopy(contract)
    unsafe["readiness_policy"]["plan_alone_may_clear_task33"] = True
    monkeypatch.setattr(adapter, "_strict_loads", lambda text: unsafe)
    with pytest.raises(
        adapter.ProductionOuterAdapterError, match="readiness policy is unsafe"
    ):
        adapter.load_production_outer_adapter_contract(REPO_ROOT)
    monkeypatch.undo()

    payload = planned.to_dict()
    payload["task33"]["plan_may_clear_blocker"] = True
    with pytest.raises(
        adapter.ProductionOuterAdapterError, match="overclaims readiness"
    ):
        adapter.validate_production_outer_adapter_plan(
            payload, repo_root=REPO_ROOT
        )


def test_plan_write_is_create_only(
    planned, tmp_path: Path
) -> None:
    target = tmp_path / "plans" / "adapter.json"
    assert adapter.write_production_outer_adapter_plan(
        planned, target, repo_root=REPO_ROOT
    ) == target
    assert json.loads(target.read_text(encoding="utf-8")) == planned.to_dict()
    with pytest.raises(
        adapter.ProductionOuterAdapterError, match="create-only"
    ):
        adapter.write_production_outer_adapter_plan(
            planned, target, repo_root=REPO_ROOT
        )
