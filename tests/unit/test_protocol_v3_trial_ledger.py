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
    TrialRecord,
    append_trial,
    assert_release_decision_allowed,
    attach_trial_daily_series,
    attest_complete_trial_inventory,
    build_canonical_historical_import_digest,
    build_historical_reconciliation_evidence_sha256,
    build_trial_inventory_evidence_sha256,
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


def _bootstrap_two_observed_rows(tmp_path: Path):
    repo_root = tmp_path / "fixture_repo"
    config_path = repo_root / "configs" / "protocol_v3_historical_trial_lower_bound.json"
    config_path.parent.mkdir(parents=True)
    payload = json.loads(
        (REPO_ROOT / "configs/protocol_v3_historical_trial_lower_bound.json").read_text(
            encoding="utf-8"
        )
    )
    payload["known_observed_evaluation_rows"] = 2
    payload["sources"] = [
        {
            "source_id": "legacy_loop_fixture",
            "source_kind": "protocol_v2_research_loop_summary",
            "observed_cycles": 1,
            "observed_tested_rows_per_cycle": 2,
            "observed_evaluation_rows": 2,
            "candidate_identity_inventory_available": False,
            "causal_daily_series_available": False,
            "evidence_reference": "legacy.json",
        }
    ]
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    root = tmp_path / "two_row_trial_ledger"
    snapshot = import_canonical_historical_lower_bound(root, repo_root)
    return root, snapshot


def _complete_historical_record(
    candidate_id: str,
    seed: int,
    *,
    source_sha256: str,
    observation_key: str,
) -> TrialRecord:
    native = _record(candidate_id, seed=seed)
    payload = native.payload()
    payload["identity_basis"]["source_kind"] = "historical_import"
    payload["historical_trial_count_is_lower_bound"] = True
    payload["historical_source_sha256"] = source_sha256
    payload["historical_observation_key"] = observation_key
    identity_json = json.dumps(
        payload["identity_basis"],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return TrialRecord(
        trial_id="trial_sha256:"
        + hashlib.sha256(identity_json.encode("utf-8")).hexdigest(),
        payload_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        canonical_payload_json=canonical,
    )


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
    assert snapshot.status.permanent_trial_count_lower_bound == 0
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
    assert snapshot.status.known_observed_historical_evaluation_rows == 182
    assert snapshot.status.permanent_trial_count_lower_bound == 0
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

    conflicting_report = _protocol_v2_report()
    conflicting_report["cycles"][0]["generated_candidate_inventory"][0][
        "params"
    ]["lookback"] = 21
    conflicting_path = tmp_path / "conflicting_same_source.json"
    conflicting_path.write_text(
        json.dumps(conflicting_report), encoding="utf-8"
    )
    event_count_before_conflict = read_trial_ledger(root).status.event_count
    with pytest.raises(TrialLedgerError, match="conflicting artifacts"):
        import_historical_reports(root, [conflicting_path])
    assert read_trial_ledger(root).status.event_count == event_count_before_conflict

    second_report = _protocol_v2_report()
    second_report["loop_run_id"] = "independent_legacy_loop_fixture"
    second_path = tmp_path / "independent.json"
    second_path.write_text(json.dumps(second_report), encoding="utf-8")
    import_historical_reports(root, [second_path])
    after_second_source = read_trial_ledger(root)
    assert (
        after_second_source.status.known_observed_historical_evaluation_rows
        == 184
    )
    assert after_second_source.status.permanent_trial_count_lower_bound == 0


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
        "duplicate_or_cache_row_count": 180,
        "mapped_observed_evaluation_rows": 182,
        "observation_mapping_sha256": "2" * 64,
        "resolved_historical_trial_count": 2,
    }
    with pytest.raises(TrialLedgerError, match="per-row mapping evidence"):
        attest_complete_trial_inventory(
            root,
            expected_resolved_trial_count=2,
            inventory_sha256="3" * 64,
            attestor="fixture",
            historical_reconciliation=reconciliation,
        )

    incomplete_mapping = dict(reconciliation)
    incomplete_mapping["mapped_observed_evaluation_rows"] = 181
    with pytest.raises(TrialLedgerError, match="every observed"):
        attest_complete_trial_inventory(
            root,
            expected_resolved_trial_count=2,
            inventory_sha256="3" * 64,
            attestor="fixture",
            historical_reconciliation=incomplete_mapping,
        )

    wrong_duplicates = dict(reconciliation)
    wrong_duplicates["duplicate_or_cache_row_count"] = 179
    with pytest.raises(TrialLedgerError, match="must equal observed"):
        attest_complete_trial_inventory(
            root,
            expected_resolved_trial_count=2,
            inventory_sha256="3" * 64,
            attestor="fixture",
            historical_reconciliation=wrong_duplicates,
        )



def test_attestation_rejects_unresolved_historical_metadata_even_with_real_digests(
    tmp_path: Path,
) -> None:
    root, _ = _bootstrap_two_observed_rows(tmp_path)
    report_path = tmp_path / "legacy.json"
    report_path.write_text(json.dumps(_protocol_v2_report()), encoding="utf-8")
    import_historical_reports(root, [report_path])
    snapshot = read_trial_ledger(root)
    assert snapshot.status.known_observed_historical_evaluation_rows == 2

    for trial_id in sorted(snapshot.trials):
        attach_trial_daily_series(
            root,
            trial_id=trial_id,
            daily_net_mtm_usdc=_daily(),
            provenance={"source": "verified_reconstruction"},
        )
    snapshot = read_trial_ledger(root)
    reconciliation = {
        "all_observed_rows_mapped": True,
        "all_historical_daily_series_complete": True,
        "duplicate_or_cache_row_count": 0,
        "mapped_observed_evaluation_rows": 2,
        "observation_mapping_sha256": (
            build_historical_reconciliation_evidence_sha256(snapshot)
        ),
        "resolved_historical_trial_count": 2,
    }
    with pytest.raises(TrialLedgerError, match="remain unresolved"):
        attest_complete_trial_inventory(
            root,
            expected_resolved_trial_count=2,
            inventory_sha256=build_trial_inventory_evidence_sha256(snapshot),
            attestor="fixture",
            historical_reconciliation=reconciliation,
        )
    assert (
        read_trial_ledger(root).status.development_dsr_status
        == DEVELOPMENT_DSR_INSUFFICIENT
    )


def test_complete_historical_trial_requires_source_and_observation_binding(
    tmp_path: Path,
) -> None:
    root, _ = _bootstrap_two_observed_rows(tmp_path)
    record = _complete_historical_record(
        "unbound_historical",
        100,
        source_sha256="1" * 64,
        observation_key="observation_sha256:" + "2" * 64,
    )
    payload = record.payload()
    payload.pop("historical_source_sha256")
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    unbound = TrialRecord(
        trial_id=record.trial_id,
        payload_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        canonical_payload_json=canonical,
    )
    with pytest.raises(TrialLedgerError, match="source digest"):
        append_trial(root, unbound)


def test_self_consistent_but_unimported_historical_source_cannot_unlock(
    tmp_path: Path,
) -> None:
    root, _ = _bootstrap_two_observed_rows(tmp_path)
    append_trial(
        root,
        _complete_historical_record(
            "unproven_a",
            91,
            source_sha256="1" * 64,
            observation_key="observation_sha256:" + "2" * 64,
        ),
    )
    snapshot = append_trial(
        root,
        _complete_historical_record(
            "unproven_b",
            92,
            source_sha256="1" * 64,
            observation_key="observation_sha256:" + "3" * 64,
        ),
    )
    reconciliation = {
        "all_observed_rows_mapped": True,
        "all_historical_daily_series_complete": True,
        "duplicate_or_cache_row_count": 0,
        "mapped_observed_evaluation_rows": 2,
        "observation_mapping_sha256": (
            build_historical_reconciliation_evidence_sha256(snapshot)
        ),
        "resolved_historical_trial_count": 2,
    }
    with pytest.raises(TrialLedgerError, match="immutable source artifacts"):
        attest_complete_trial_inventory(
            root,
            expected_resolved_trial_count=2,
            inventory_sha256=build_trial_inventory_evidence_sha256(snapshot),
            attestor="fixture",
            historical_reconciliation=reconciliation,
        )
    assert read_trial_ledger(root).status.historical_trial_count_is_lower_bound


def test_attestation_is_checked_at_its_event_and_later_native_trial_is_valid(
    tmp_path: Path,
) -> None:
    root, _ = _bootstrap_two_observed_rows(tmp_path)
    evidence_report = {
        "schema_version": 2,
        "loop_run_id": "legacy_loop_fixture",
        "cycles": [{"cycle_id": 1, "tested_candidates": 2}],
    }
    evidence_path = tmp_path / "immutable_historical_evidence.json"
    evidence_path.write_text(json.dumps(evidence_report), encoding="utf-8")
    source_sha256 = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    import_result = import_historical_reports(root, [evidence_path])
    assert import_result.imported_trial_count == 0
    assert import_result.skipped_candidate_count == 2

    def observation_key(row_index: int) -> str:
        basis = json.dumps(
            {"source_sha256": source_sha256, "row_index": row_index},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return "observation_sha256:" + hashlib.sha256(
            basis.encode("utf-8")
        ).hexdigest()

    append_trial(
        root,
        _complete_historical_record(
            "historical_a",
            101,
            source_sha256=source_sha256,
            observation_key=observation_key(1),
        ),
    )
    snapshot = append_trial(
        root,
        _complete_historical_record(
            "historical_b",
            102,
            source_sha256=source_sha256,
            observation_key=observation_key(2),
        ),
    )
    reconciliation = {
        "all_observed_rows_mapped": True,
        "all_historical_daily_series_complete": True,
        "duplicate_or_cache_row_count": 0,
        "mapped_observed_evaluation_rows": 2,
        "observation_mapping_sha256": (
            build_historical_reconciliation_evidence_sha256(snapshot)
        ),
        "resolved_historical_trial_count": 2,
    }
    attested = attest_complete_trial_inventory(
        root,
        expected_resolved_trial_count=2,
        inventory_sha256=build_trial_inventory_evidence_sha256(snapshot),
        attestor="fixture",
        historical_reconciliation=reconciliation,
    )
    assert attested.status.historical_trial_count_is_lower_bound is False
    assert attested.status.development_dsr_status == DEVELOPMENT_DSR_READY

    after_native = append_trial(root, _record("later_native", seed=103))
    assert after_native.status.resolved_trial_count == 3
    assert after_native.status.permanent_trial_count_lower_bound == 3
    assert after_native.status.historical_trial_count_is_lower_bound is False
    assert after_native.status.development_dsr_status == DEVELOPMENT_DSR_READY
    assert_release_decision_allowed(after_native, TRADING_CANDIDATE)


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


def test_stale_head_at_valid_event_prefix_recovers_after_event_first_crash(
    tmp_path: Path,
) -> None:
    root, _ = _bootstrap(tmp_path)
    append_trial(root, _record())
    first_event = json.loads(
        sorted((root / "events").glob("*.json"))[0].read_text(
            encoding="utf-8"
        )
    )
    stale_body = {
        "schema_version": "protocol_v3_trial_ledger_head_v1",
        "event_count": 1,
        "event_head_sha256": first_event["event_sha256"],
        "resolved_trial_count": 0,
    }
    stale_head = {
        **stale_body,
        "head_sha256": hashlib.sha256(
            json.dumps(
                stale_body,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
        ).hexdigest(),
    }
    (root / "head.json").write_text(
        json.dumps(stale_head), encoding="utf-8"
    )

    recovered = read_trial_ledger(root)
    assert recovered.status.event_count == 2
    assert recovered.status.resolved_trial_count == 1
    assert recovered.status.head_sha256 == recovered.events[-1]["event_sha256"]

    healed = append_trial(root, _record("after_crash", seed=12))
    persisted_head = json.loads(
        (root / "head.json").read_text(encoding="utf-8")
    )
    assert persisted_head["event_count"] == healed.status.event_count
    assert persisted_head["event_head_sha256"] == healed.status.head_sha256


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

    refit_id = "a" * 64
    usage = GlobalBudgetUsage()
    for origin_index in range(1, 13):
        for _ in range(8):
            usage = usage.reserve_origin_cycle(origin_index)
    assert usage.total_cycles == 96
    usage = usage.start_current_refit(refit_id)
    for _ in range(8):
        usage = usage.reserve_current_refit_cycle(refit_id)
    validate_global_budget_usage(usage)
    assert usage.total_cycles == 104
    assert usage.reserved_generated == 4160
    assert usage.reserved_tested == 1248
    assert usage.reserved_walk_forward == 312
    assert usage.reserved_finalists == 208
    with pytest.raises(Exception, match="current refit exceeds"):
        usage.reserve_current_refit_cycle(refit_id)

    usage = usage.complete_current_refit(refit_id)
    with pytest.raises(Exception, match="already completed"):
        usage.reserve_current_refit_cycle(refit_id)


def test_global_budget_forgery_and_second_current_refit_are_impossible() -> None:
    refit_id = "a" * 64
    usage = (
        GlobalBudgetUsage()
        .start_current_refit(refit_id)
        .reserve_current_refit_cycle(refit_id)
    )
    with pytest.raises(Exception, match="does not match"):
        validate_global_budget_usage(replace(usage, reserved_generated=39))
    with pytest.raises(Exception, match="twelve origin"):
        validate_global_budget_usage(replace(usage, cycles_by_origin=(0,)))
    with pytest.raises(Exception, match="remain 12 origins plus one"):
        replace(GlobalSearchBudgetEnvelope(), current_refit_runs=2).validate()
    with pytest.raises(Exception, match="second current refit"):
        usage.start_current_refit("b" * 64)
    with pytest.raises(Exception, match="second current refit"):
        usage.reserve_current_refit_cycle("b" * 64)
    with pytest.raises(Exception, match="must be started"):
        GlobalBudgetUsage().reserve_current_refit_cycle(refit_id)
    with pytest.raises(Exception, match="frozen refit identity"):
        validate_global_budget_usage(
            replace(GlobalBudgetUsage(), current_refit_cycles=1)
        )
