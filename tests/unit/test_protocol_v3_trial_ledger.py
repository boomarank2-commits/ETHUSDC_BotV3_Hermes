"""Task-4 tests for the permanent Protocol v3 trial ledger."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil

import pytest

import ethusdc_bot.protocol_v3.trial_ledger as ledger_module
from ethusdc_bot.protocol_v3 import (
    DEVELOPMENT_DSR_INSUFFICIENT,
    DEVELOPMENT_DSR_READY,
    MAX_TOTAL_CYCLES,
    MAX_TOTAL_FINALISTS,
    MAX_TOTAL_GENERATED,
    MAX_TOTAL_TESTED,
    MAX_TOTAL_WALK_FORWARD,
    NO_TRADE,
    TRADING_CANDIDATE,
    GlobalBudgetUsage,
    GlobalSearchBudgetEnvelope,
    TrialLedgerError,
    append_trial,
    assert_release_decision_allowed,
    attach_trial_daily_series,
    attest_complete_trial_inventory,
    build_canonical_historical_import_digest,
    build_trial_record,
    import_canonical_historical_lower_bound,
    import_historical_reports,
    read_trial_ledger,
    record_cache_reuse,
    validate_global_budget_usage,
    validate_historical_lower_bound_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMIT = "a" * 40
VERSIONS = {
    "pipeline_generation": "protocol_v3_pipeline_sha256:" + "1" * 64,
    "ranking_version": "protocol_v3_lexicographic_inner_ranking_v1",
    "gate_version": "monthly_quality_gate_v1",
    "simulator_version": "conservative_spot_long_only_v1",
    "cost_model_version": "fee_10bps_slippage_5bps_v1",
    "boundary_version": "protocol_v3_monthly_boundary_v1",
}


def _daily(offset: float = 0.0) -> list[dict[str, object]]:
    return [
        {"day": "2025-01-01", "net_usdc": 0.1 + offset},
        {"day": "2025-01-02", "net_usdc": -0.05 + offset},
        {"day": "2025-01-03", "net_usdc": 0.0 + offset},
    ]


def _record(
    candidate_id: str = "candidate_a",
    *,
    source_kind: str = "native_evaluation",
    result: float = 0.05,
    seed: int = 11,
):
    return build_trial_record(
        source_kind=source_kind,
        candidate_id=candidate_id,
        family="breakout_volatility_filter",
        parameters={"lookback": 20, "symbol": "ETHUSDC"},
        feature_variant="causal_feature_set_v1",
        seed=seed,
        versions=VERSIONS,
        code_commit=COMMIT,
        evaluation_scope={
            "origin_index": 1,
            "cycle_index": 1,
            "fold_plan": "six_by_sixty_v1",
        },
        daily_net_mtm_usdc=_daily(),
        result_summary={"net_usdc_per_day": result},
    )


def _bootstrap(tmp_path: Path):
    root = tmp_path / "trial_ledger"
    snapshot = import_canonical_historical_lower_bound(root, REPO_ROOT)
    return root, snapshot


def _protocol_v2_report() -> dict[str, object]:
    def inventory(candidate_id: str, lookback: int) -> dict[str, object]:
        return {
            "candidate_id": candidate_id,
            "family": "breakout_volatility_filter",
            "params": {"lookback": lookback, "symbol": "ETHUSDC"},
            "tested": True,
        }

    return {
        "schema_version": 2,
        "loop_run_id": "legacy_loop_fixture",
        "git_commit": COMMIT,
        "quality_gate_version": "quality_gate_v1",
        "research_protocol": {"schema_version": 2},
        "cycles": [
            {
                "cycle_id": 1,
                "tested_candidates": 2,
                "candidate_stage_ids": {
                    "generated": ["legacy_a", "legacy_b"],
                    "tested": ["legacy_a", "legacy_b"],
                    "walk_forward": ["legacy_a"],
                    "finalists": ["legacy_a"],
                },
                "generated_candidate_inventory": [
                    inventory("legacy_a", 20),
                    inventory("legacy_b", 30),
                ],
                "selected_candidate": {"candidate_id": "legacy_a"},
                "selected_candidate_score": {
                    "ranking_rule": "legacy_ranking_v2",
                    "wfv_net_usdc_per_day": -0.01,
                },
                "quality_gate": {
                    "gate_version": "quality_gate_v1",
                    "passed": False,
                },
            }
        ],
    }


def test_canonical_historical_import_is_an_honest_lower_bound(tmp_path: Path) -> None:
    root, snapshot = _bootstrap(tmp_path)

    assert snapshot.status.event_count == 1
    assert snapshot.status.resolved_trial_count == 0
    assert snapshot.status.known_observed_historical_evaluation_rows == 180
    assert snapshot.status.permanent_trial_count_lower_bound == 180
    assert snapshot.status.historical_trial_count_is_lower_bound is True
    assert snapshot.status.canonical_historical_import_present is True
    assert snapshot.status.development_dsr_status == DEVELOPMENT_DSR_INSUFFICIENT
    assert snapshot.status.only_release_decision_allowed == NO_TRADE
    assert_release_decision_allowed(snapshot, NO_TRADE)
    with pytest.raises(TrialLedgerError, match="NO_TRADE only"):
        assert_release_decision_allowed(snapshot, TRADING_CANDIDATE)

    repeated = import_canonical_historical_lower_bound(root, REPO_ROOT)
    assert repeated.status.event_count == 1


def test_native_trial_id_is_deterministic_and_append_is_idempotent(tmp_path: Path) -> None:
    root, _ = _bootstrap(tmp_path)
    first = _record()
    second = _record()

    assert first == second
    assert first.trial_id.startswith("trial_sha256:")
    snapshot = append_trial(root, first)
    assert snapshot.status.resolved_trial_count == 1
    assert snapshot.status.native_trial_count == 1
    assert snapshot.status.event_count == 2

    repeated = append_trial(root, second)
    assert repeated.status.resolved_trial_count == 1
    assert repeated.status.event_count == 2
    stored = repeated.trials[first.trial_id]
    assert stored["identity_basis"]["candidate"]["candidate_id"] == "candidate_a"
    assert stored["identity_basis"]["seed"] == 11
    assert stored["identity_basis"]["versions"] == dict(sorted(VERSIONS.items()))
    assert stored["daily_net_mtm_usdc"] == _daily()


def test_same_trial_identity_cannot_be_silently_rewritten(tmp_path: Path) -> None:
    root, _ = _bootstrap(tmp_path)
    original = _record(result=0.05)
    append_trial(root, original)
    changed = _record(result=999.0)

    assert changed.trial_id == original.trial_id
    with pytest.raises(TrialLedgerError, match="different immutable payload"):
        append_trial(root, changed)


def test_manual_patch_after_results_is_permanently_counted(tmp_path: Path) -> None:
    root, _ = _bootstrap(tmp_path)
    native = _record()
    manual = _record(source_kind="manual_patch_after_results")
    assert manual.trial_id != native.trial_id

    append_trial(root, native)
    snapshot = append_trial(root, manual)
    assert snapshot.status.resolved_trial_count == 2
    assert snapshot.status.native_trial_count == 2
    assert snapshot.status.development_dsr_status == DEVELOPMENT_DSR_INSUFFICIENT


def test_cache_reuse_is_visible_but_never_an_independent_trial(tmp_path: Path) -> None:
    root, _ = _bootstrap(tmp_path)
    record = _record()
    snapshot = append_trial(root, record)
    assert snapshot.status.resolved_trial_count == 1

    reused = record_cache_reuse(
        root,
        trial_id=record.trial_id,
        reuse_scope={"origin_index": 2, "cycle_index": 1},
    )
    assert reused.status.cache_reuse_count == 1
    assert reused.status.resolved_trial_count == 1
    assert reused.events[-1]["payload"]["counts_as_independent_trial"] is False

    repeated = record_cache_reuse(
        root,
        trial_id=record.trial_id,
        reuse_scope={"origin_index": 2, "cycle_index": 1},
    )
    assert repeated.status.cache_reuse_count == 1
    assert repeated.status.event_count == reused.status.event_count

    with pytest.raises(TrialLedgerError, match="unknown trial"):
        record_cache_reuse(
            root,
            trial_id="trial_sha256:" + "f" * 64,
            reuse_scope={"origin_index": 3},
        )


def test_native_daily_series_is_required_ordered_unique_and_finite() -> None:
    common = dict(
        source_kind="native_evaluation",
        candidate_id="candidate",
        family="breakout_volatility_filter",
        parameters={"symbol": "ETHUSDC"},
        feature_variant="features_v1",
        seed=1,
        versions=VERSIONS,
        code_commit=COMMIT,
        evaluation_scope={"origin_index": 1},
        result_summary={},
    )
    with pytest.raises(TrialLedgerError, match="must not be empty"):
        build_trial_record(daily_net_mtm_usdc=[], **common)
    with pytest.raises(TrialLedgerError, match="strictly increasing"):
        build_trial_record(
            daily_net_mtm_usdc=[
                {"day": "2025-01-02", "net_usdc": 0.0},
                {"day": "2025-01-01", "net_usdc": 0.0},
            ],
            **common,
        )
    with pytest.raises(TrialLedgerError, match="strictly increasing"):
        build_trial_record(
            daily_net_mtm_usdc=[
                {"day": "2025-01-01", "net_usdc": 0.0},
                {"day": "2025-01-01", "net_usdc": 0.0},
            ],
            **common,
        )
    with pytest.raises(TrialLedgerError, match="non-finite"):
        build_trial_record(
            daily_net_mtm_usdc=[
                {"day": "2025-01-01", "net_usdc": float("nan")}
            ],
            **common,
        )


def test_historical_protocol_v2_import_is_deterministic_and_lower_bound(
    tmp_path: Path,
) -> None:
    root, _ = _bootstrap(tmp_path)
    report_path = tmp_path / "legacy.json"
    report_path.write_text(json.dumps(_protocol_v2_report()), encoding="utf-8")

    result = import_historical_reports(root, [report_path])
    snapshot = read_trial_ledger(root)
    assert result.source_count == 1
    assert result.imported_trial_count == 2
    assert result.reused_trial_count == 0
    assert result.observed_evaluation_rows == 2
    assert snapshot.status.resolved_trial_count == 2
    assert snapshot.status.historical_resolved_trial_count == 2
    assert len(snapshot.status.missing_daily_series_trial_ids) == 2
    assert snapshot.status.historical_trial_count_is_lower_bound is True
    assert snapshot.status.known_observed_historical_evaluation_rows == 180
    assert snapshot.status.development_dsr_status == DEVELOPMENT_DSR_INSUFFICIENT

    repeated = import_historical_reports(root, [report_path])
    after = read_trial_ledger(root)
    assert repeated.imported_trial_count == 0
    assert repeated.reused_trial_count == 2
    assert after.status.resolved_trial_count == 2
    assert after.status.event_count == snapshot.status.event_count

    copied_path = tmp_path / "same_bytes_copy.json"
    shutil.copyfile(report_path, copied_path)
    copied = import_historical_reports(root, [copied_path])
    assert copied.imported_trial_count == 0
    assert copied.reused_trial_count == 2


def test_historical_daily_series_attachment_is_append_only(tmp_path: Path) -> None:
    root, _ = _bootstrap(tmp_path)
    report_path = tmp_path / "legacy.json"
    report_path.write_text(json.dumps(_protocol_v2_report()), encoding="utf-8")
    import_historical_reports(root, [report_path])
    snapshot = read_trial_ledger(root)
    trial_id = sorted(snapshot.trials)[0]

    attached = attach_trial_daily_series(
        root,
        trial_id=trial_id,
        daily_net_mtm_usdc=_daily(),
        provenance={"source": "reconstructed_legacy_daily_series", "verified": True},
    )
    assert trial_id not in attached.status.missing_daily_series_trial_ids
    assert list(attached.attached_daily_series[trial_id]) == _daily()

    repeated = attach_trial_daily_series(
        root,
        trial_id=trial_id,
        daily_net_mtm_usdc=_daily(),
        provenance={"source": "different_note_but_same_series"},
    )
    assert repeated.status.event_count == attached.status.event_count
    with pytest.raises(TrialLedgerError, match="conflicts"):
        attach_trial_daily_series(
            root,
            trial_id=trial_id,
            daily_net_mtm_usdc=_daily(1.0),
            provenance={"source": "changed"},
        )


def test_lower_bound_cannot_clear_without_full_reconciliation(tmp_path: Path) -> None:
    root, _ = _bootstrap(tmp_path)
    report_path = tmp_path / "legacy.json"
    report_path.write_text(json.dumps(_protocol_v2_report()), encoding="utf-8")
    import_historical_reports(root, [report_path])
    snapshot = read_trial_ledger(root)

    reconciliation = {
        "all_observed_rows_mapped": True,
        "all_historical_daily_series_complete": True,
        "duplicate_or_cache_row_count": 178,
        "mapped_observed_evaluation_rows": 180,
        "observation_mapping_sha256": "2" * 64,
        "resolved_historical_trial_count": 2,
    }
    with pytest.raises(TrialLedgerError, match="daily series"):
        attest_complete_trial_inventory(
            root,
            expected_resolved_trial_count=2,
            inventory_sha256="3" * 64,
            attestor="fixture",
            historical_reconciliation=reconciliation,
        )

    for trial_id in sorted(snapshot.trials):
        attach_trial_daily_series(
            root,
            trial_id=trial_id,
            daily_net_mtm_usdc=_daily(),
            provenance={"source": "verified_reconstruction"},
        )

    incomplete_mapping = dict(reconciliation)
    incomplete_mapping["mapped_observed_evaluation_rows"] = 179
    with pytest.raises(TrialLedgerError, match="every observed"):
        attest_complete_trial_inventory(
            root,
            expected_resolved_trial_count=2,
            inventory_sha256="3" * 64,
            attestor="fixture",
            historical_reconciliation=incomplete_mapping,
        )

    wrong_duplicates = dict(reconciliation)
    wrong_duplicates["duplicate_or_cache_row_count"] = 177
    with pytest.raises(TrialLedgerError, match="must equal observed"):
        attest_complete_trial_inventory(
            root,
            expected_resolved_trial_count=2,
            inventory_sha256="3" * 64,
            attestor="fixture",
            historical_reconciliation=wrong_duplicates,
        )

    complete = attest_complete_trial_inventory(
        root,
        expected_resolved_trial_count=2,
        inventory_sha256="3" * 64,
        attestor="fixture",
        historical_reconciliation=reconciliation,
    )
    assert complete.status.historical_trial_count_is_lower_bound is False
    assert complete.status.missing_daily_series_trial_ids == ()
    assert complete.status.development_dsr_status == DEVELOPMENT_DSR_READY
    assert complete.status.only_release_decision_allowed is None
    assert_release_decision_allowed(complete, TRADING_CANDIDATE)


def test_direct_trial_ledger_submodule_uses_reconciled_attestation_gate() -> None:
    assert ledger_module.attest_complete_trial_inventory is attest_complete_trial_inventory


def test_event_tampering_deletion_and_head_rewrite_are_detected(tmp_path: Path) -> None:
    root, _ = _bootstrap(tmp_path)
    append_trial(root, _record())
    clean = root / "clean_copy"
    shutil.copytree(root, clean)

    event_path = sorted((root / "events").glob("*.json"))[-1]
    event = json.loads(event_path.read_text(encoding="utf-8"))
    event["payload"]["trial"]["result_summary"]["net_usdc_per_day"] = 999.0
    event_path.write_text(json.dumps(event), encoding="utf-8")
    with pytest.raises(TrialLedgerError, match="digest|filename"):
        read_trial_ledger(root)

    deletion = tmp_path / "deleted_tail"
    shutil.copytree(clean, deletion)
    sorted((deletion / "events").glob("*.json"))[-1].unlink()
    with pytest.raises(TrialLedgerError, match="head"):
        read_trial_ledger(deletion)

    head_rewrite = tmp_path / "rewritten_head"
    shutil.copytree(clean, head_rewrite)
    head_path = head_rewrite / "head.json"
    head = json.loads(head_path.read_text(encoding="utf-8"))
    head["resolved_trial_count"] = 999
    head_path.write_text(json.dumps(head), encoding="utf-8")
    with pytest.raises(TrialLedgerError, match="head digest|head does not match"):
        read_trial_ledger(head_rewrite)


def test_stale_lock_fails_closed(tmp_path: Path) -> None:
    root, _ = _bootstrap(tmp_path)
    record = _record()
    append_trial(root, record)
    (root / ".ledger.lock").write_text("stale", encoding="utf-8")
    with pytest.raises(TrialLedgerError, match="locked"):
        record_cache_reuse(
            root,
            trial_id=record.trial_id,
            reuse_scope={"origin_index": 2},
        )


def test_historical_lower_bound_contract_cannot_be_relaxed() -> None:
    path = REPO_ROOT / "configs/protocol_v3_historical_trial_lower_bound.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_historical_lower_bound_manifest(payload)
    assert build_canonical_historical_import_digest(REPO_ROOT) == hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()

    changed = json.loads(json.dumps(payload))
    changed["historical_trial_count_is_lower_bound"] = False
    with pytest.raises(TrialLedgerError, match="lower bound"):
        validate_historical_lower_bound_manifest(changed)

    changed = json.loads(json.dumps(payload))
    changed["interpretation"]["only_release_decision_allowed"] = TRADING_CANDIDATE
    with pytest.raises(TrialLedgerError, match="fail-closed"):
        validate_historical_lower_bound_manifest(changed)


def test_combined_global_budget_includes_exactly_one_current_refit() -> None:
    envelope = GlobalSearchBudgetEnvelope()
    envelope.validate()
    assert envelope.selection_run_count == 13
    assert (
        MAX_TOTAL_CYCLES,
        MAX_TOTAL_GENERATED,
        MAX_TOTAL_TESTED,
        MAX_TOTAL_WALK_FORWARD,
        MAX_TOTAL_FINALISTS,
    ) == (104, 4160, 1248, 312, 208)

    usage = GlobalBudgetUsage()
    for origin_index in range(1, 13):
        for _ in range(8):
            usage = usage.reserve_origin_cycle(origin_index)
    assert usage.total_cycles == 96
    for _ in range(8):
        usage = usage.reserve_current_refit_cycle()
    validate_global_budget_usage(usage)
    assert usage.total_cycles == 104
    assert usage.reserved_generated == 4160
    assert usage.reserved_tested == 1248
    assert usage.reserved_walk_forward == 312
    assert usage.reserved_finalists == 208
    with pytest.raises(Exception, match="current refit exceeds"):
        usage.reserve_current_refit_cycle()


def test_global_budget_forgery_and_second_current_refit_are_impossible() -> None:
    usage = GlobalBudgetUsage().reserve_current_refit_cycle()
    with pytest.raises(Exception, match="does not match"):
        validate_global_budget_usage(replace(usage, reserved_generated=39))
    with pytest.raises(Exception, match="twelve origin"):
        validate_global_budget_usage(replace(usage, cycles_by_origin=(0,)))
    with pytest.raises(Exception, match="remain 12 origins plus one"):
        replace(GlobalSearchBudgetEnvelope(), current_refit_runs=2).validate()
