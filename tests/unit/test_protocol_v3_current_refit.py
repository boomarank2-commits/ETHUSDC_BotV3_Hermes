"""Task-28 tests for the current 730-day refit decision envelope."""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from ethusdc_bot.backtest.simulator import StrategyCandidate
from ethusdc_bot.protocol_v3 import boundaries, current_refit, current_refit_api
from ethusdc_bot.protocol_v3 import inner_folds, inner_selection, outer_origins
from ethusdc_bot.protocol_v3 import pipeline, router_bundle
from ethusdc_bot.protocol_v3.pipeline import build_pre_run_manifest

REPO_ROOT = Path(__file__).resolve().parents[2]
_TASK27_PATH = Path(__file__).with_name(
    "test_protocol_v3_historical_diagnostics.py"
)
_SPEC27 = importlib.util.spec_from_file_location(
    "protocol_v3_task28_task27_support", _TASK27_PATH
)
assert _SPEC27 is not None and _SPEC27.loader is not None
task27 = importlib.util.module_from_spec(_SPEC27)
_SPEC27.loader.exec_module(task27)

_TASK23_PATH = Path(__file__).with_name("test_protocol_v3_outer_origins.py")
_SPEC23 = importlib.util.spec_from_file_location(
    "protocol_v3_task28_task23_support", _TASK23_PATH
)
assert _SPEC23 is not None and _SPEC23.loader is not None
task23 = importlib.util.module_from_spec(_SPEC23)
_SPEC23.loader.exec_module(task23)

_TASK15_PATH = Path(__file__).with_name("test_protocol_v3_inner_selection.py")
_SPEC15 = importlib.util.spec_from_file_location(
    "protocol_v3_task28_task15_support", _TASK15_PATH
)
assert _SPEC15 is not None and _SPEC15.loader is not None
task15 = importlib.util.module_from_spec(_SPEC15)
_SPEC15.loader.exec_module(task15)


def _current_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    current_plan,
    *,
    snapshot_day=None,
):
    origin = current_plan.origins[-1]
    frozen_day = snapshot_day or (origin.test_start_inclusive - timedelta(days=1))
    monkeypatch.setattr(task23.support._FakeInspector, "latest_day", frozen_day)
    monkeypatch.setattr(
        task23.support._FakeInspector,
        "first_day",
        frozen_day - timedelta(days=1200),
    )
    base = task23.support.build_state(tmp_path / "current", monkeypatch)
    generation = pipeline.build_pipeline_generation(REPO_ROOT)
    manifest = build_pre_run_manifest(
        generation,
        current_plan,
        code_commit=task23.support.COMMIT,
    )
    fold_plan = inner_folds.build_inner_fold_plan_for_origin(
        origin,
        task23.support.HORIZON,
        repo_root=REPO_ROOT,
    )
    config = inner_selection.build_frozen_selection_config(
        pre_run_manifest=manifest,
        run_fingerprint=base["fingerprint"],
        fold_identity=fold_plan.identity_payload,
        origin_index=origin.origin_index,
        cycle_index=1,
        generated_candidate_ids=[],
        tested_candidate_ids=[],
        walk_forward_candidate_ids=[],
        finalist_candidate_ids=[],
        candidate_evidence=[],
        development_support=inner_selection.build_incomplete_development_support(
            "no_complete_local_edge_evidence"
        ),
    )
    context_ms = int(
        datetime(
            origin.test_start_inclusive.year,
            origin.test_start_inclusive.month,
            origin.test_start_inclusive.day,
            tzinfo=UTC,
        ).timestamp()
        * 1000
    )
    store = SimpleNamespace(
        to_dict=lambda value=context_ms: {
            "common_context_timestamp_ms": value
        }
    )
    assessment = SimpleNamespace(
        to_dict=lambda value=context_ms: {"context_timestamp_ms": value}
    )
    feature_state = SimpleNamespace(
        to_dict=lambda value=fold_plan.identity_payload: {
            "fold_identity": value
        }
    )
    regime_state = SimpleNamespace(
        to_dict=lambda value=fold_plan.identity_payload: {
            "fold_identity": value
        }
    )
    return outer_origins.OuterOriginRequest(
        config,
        None,
        store,
        object(),
        feature_state,
        regime_state,
        assessment,
    )


def _install_predecessor_aware_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    original = outer_origins.build_frozen_candidate_bundle

    def wrapper(route, decision, local_edge, **kwargs):
        frozen = original(route, decision, local_edge, **kwargs)
        payload = frozen.to_dict()
        payload["predecessor_bundle_sha256"] = kwargs.get(
            "predecessor_bundle_sha256"
        )
        basis = dict(payload)
        basis.pop("bundle_sha256")
        return router_bundle.FrozenCandidateBundle(
            outer_origins._canonical(basis),
            outer_origins._digest(basis),
        )

    monkeypatch.setattr(outer_origins, "build_frozen_candidate_bundle", wrapper)


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    plan, process, baseline, gate, bound, diagnostics = task27.state.__wrapped__(
        tmp_path / "historical", monkeypatch
    )
    _install_predecessor_aware_fixture(monkeypatch)
    current_plan = boundaries.build_monthly_process_boundary_plan("2026-08-08")
    request = _current_request(tmp_path, monkeypatch, current_plan)
    requested = datetime(2026, 7, 8, 12, tzinfo=UTC)
    report = current_refit.build_current_refit_decision(
        historical_boundary_plan=plan,
        current_boundary_plan=current_plan,
        historical_outer_process=process,
        baseline_ledger=baseline,
        monthly_quality_report=gate,
        historical_diagnostics=diagnostics,
        current_request=request,
        requested_at_utc=requested,
    )
    return (
        plan,
        current_plan,
        process,
        baseline,
        gate,
        diagnostics,
        request,
        requested,
        report,
    )


def test_contract_api_and_pipeline_binding_are_exact() -> None:
    contract = current_refit.load_current_refit_contract(REPO_ROOT)
    assert contract["refit_policy"]["development_days"] == 730
    assert contract["decision_policy"]["choices"] == [
        current_refit.CHAMPION,
        current_refit.CHALLENGER,
        current_refit.CASH,
    ]
    assert contract["data_snapshot_policy"] == {
        "markets": ["ETHUSDC", "BTCUSDC", "ETHBTC"],
        "snapshot_as_of_day": "T-1",
        "latest_common_complete_day": "T-1",
        "raw_interval_end_exclusive": "T",
        "stale_or_future_snapshot_forbidden": True,
        "exchange_info_may_not_postdate_request": True,
    }
    assert contract["prior_evidence_policy"][
        "baseline_joint_and_slippage_ledger_hashes_required"
    ] is True
    assert current_refit_api.__all__ == current_refit.__all__


def test_current_refit_uses_exact_window_predecessor_t_plus_24_and_cash(state) -> None:
    *_, report = state
    payload = report.to_dict()
    manifest = payload["identity_manifest"]
    assert manifest["target_anchor_utc"] == "2026-07-08T00:00:00Z"
    assert manifest["training_start_inclusive"] == "2024-07-08"
    assert manifest["training_end_exclusive"] == "2026-07-08"
    assert manifest["valid_from_utc"] == "2026-07-09T00:00:00Z"
    assert manifest["valid_until_utc"] == "2026-08-08T00:00:00Z"
    assert manifest["current_snapshot_as_of_day"] == "2026-07-07"
    assert manifest["current_latest_common_complete_day"] == "2026-07-07"
    assert manifest["current_raw_interval_end_exclusive"] == (
        "2026-07-08T00:00:00Z"
    )
    assert payload["frozen_candidate_bundle"][
        "predecessor_bundle_sha256"
    ] == manifest["predecessor_bundle_sha256"]
    assert payload["outer_rotation_state"]["entry_enabled_at_utc"] == (
        manifest["valid_from_utc"]
    )
    assert payload["champion_challenger_cash_decision"]["choice"] == (
        current_refit.CASH
    )
    assert payload["outer_or_hindsight_feedback_used"] is False
    assert payload["freshness"] == "NOT_FRESH"
    assert payload["diagnostic_only"] is True
    assert payload["canonical_adoption_eligible"] is False
    assert payload["manual_research_shadow_start_required"] is True
    assert payload["manual_research_shadow_start_allowed"] is False
    assert payload["bot_start_allowed"] is False


def test_persisted_report_requires_complete_exact_source_replay(state) -> None:
    (
        plan,
        current_plan,
        process,
        baseline,
        gate,
        diagnostics,
        request,
        requested,
        report,
    ) = state
    assert (
        current_refit.validate_current_refit_decision(
            report.to_dict(),
            historical_boundary_plan=plan,
            current_boundary_plan=current_plan,
            historical_outer_process=process,
            baseline_ledger=baseline,
            monthly_quality_report=gate,
            historical_diagnostics=diagnostics,
            current_request=request,
            requested_at_utc=requested,
        )
        == report
    )
    with pytest.raises(current_refit.CurrentRefitError, match="complete source"):
        current_refit.validate_current_refit_decision(report.to_dict())


def test_late_early_or_wrong_anchor_refit_fails_closed(state) -> None:
    (
        plan,
        current_plan,
        process,
        baseline,
        gate,
        diagnostics,
        request,
        _,
        _,
    ) = state
    common = dict(
        historical_boundary_plan=plan,
        current_boundary_plan=current_plan,
        historical_outer_process=process,
        baseline_ledger=baseline,
        monthly_quality_report=gate,
        historical_diagnostics=diagnostics,
        current_request=request,
    )
    with pytest.raises(current_refit.CurrentRefitError, match=r"missed T\+24h"):
        current_refit.build_current_refit_decision(
            **common,
            requested_at_utc=datetime(2026, 7, 9, 0, 0, 1, tzinfo=UTC),
        )
    with pytest.raises(current_refit.CurrentRefitError, match="before target anchor"):
        current_refit.build_current_refit_decision(
            **common,
            requested_at_utc=datetime(2026, 7, 7, 23, 59, 59, tzinfo=UTC),
        )
    wrong = boundaries.build_monthly_process_boundary_plan("2026-09-08")
    with pytest.raises(current_refit.CurrentRefitError, match="historical process end"):
        current_refit.build_current_refit_decision(
            **{**common, "current_boundary_plan": wrong},
            requested_at_utc=datetime(2026, 7, 8, tzinfo=UTC),
        )


def test_stale_or_future_snapshot_fails_before_selection(
    state, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (
        plan,
        current_plan,
        process,
        baseline,
        gate,
        diagnostics,
        _,
        requested,
        _,
    ) = state
    target = current_plan.origins[-1].test_start_inclusive
    common = dict(
        historical_boundary_plan=plan,
        current_boundary_plan=current_plan,
        historical_outer_process=process,
        baseline_ledger=baseline,
        monthly_quality_report=gate,
        historical_diagnostics=diagnostics,
        requested_at_utc=requested,
    )
    for label, snapshot_day in (
        ("stale", target - timedelta(days=2)),
        ("future", target + timedelta(days=31)),
    ):
        request = _current_request(
            tmp_path / label,
            monkeypatch,
            current_plan,
            snapshot_day=snapshot_day,
        )
        with pytest.raises(current_refit.CurrentRefitError, match="snapshot must end"):
            current_refit.build_current_refit_decision(
                **common,
                current_request=request,
            )


def test_rehashed_rotation_or_request_time_tampering_fails(state) -> None:
    *_, report = state
    rotation = deepcopy(report.to_dict())
    rotation["outer_rotation_state"]["entry_enabled_at_utc"] = (
        "2026-07-08T12:00:00Z"
    )
    rotation_basis = dict(rotation["outer_rotation_state"])
    rotation_basis.pop("state_sha256")
    rotation["outer_rotation_state"]["state_sha256"] = current_refit._digest(
        rotation_basis
    )
    rotation["identity_manifest"]["current_rotation_state_sha256"] = rotation[
        "outer_rotation_state"
    ]["state_sha256"]
    rotation["identity_manifest_sha256"] = current_refit._digest(
        rotation["identity_manifest"]
    )
    basis = dict(rotation)
    basis.pop("report_sha256")
    forged_rotation = current_refit.CurrentRefitDecision(
        current_refit._canonical(basis), current_refit._digest(basis)
    )
    with pytest.raises(current_refit.CurrentRefitError, match="rotation state"):
        current_refit.validate_current_refit_decision(forged_rotation)

    early = deepcopy(report.to_dict())
    early["identity_manifest"]["requested_at_utc"] = "2026-07-07T23:59:59Z"
    early["identity_manifest_sha256"] = current_refit._digest(
        early["identity_manifest"]
    )
    early_basis = dict(early)
    early_basis.pop("report_sha256")
    forged_early = current_refit.CurrentRefitDecision(
        current_refit._canonical(early_basis), current_refit._digest(early_basis)
    )
    with pytest.raises(current_refit.CurrentRefitError, match=r"\[T,T\+24h\]"):
        current_refit.validate_current_refit_decision(forged_early)

    missing_stress = deepcopy(report.to_dict())
    missing_stress["prior_process_diagnostic_status"].pop(
        "joint_stress_ledger_sha256"
    )
    missing_basis = dict(missing_stress)
    missing_basis.pop("report_sha256")
    forged_missing = current_refit.CurrentRefitDecision(
        current_refit._canonical(missing_basis), current_refit._digest(missing_basis)
    )
    with pytest.raises(current_refit.CurrentRefitError, match="prior process"):
        current_refit.validate_current_refit_decision(forged_missing)


def test_pairwise_champion_challenger_and_missing_retest_are_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selection_state = task15.state.__wrapped__(tmp_path / "pairwise", monkeypatch)
    champion = StrategyCandidate("pullback_in_trend", {"lookback": 10})
    challenger = StrategyCandidate("pullback_in_trend", {"lookback": 20})
    missing = StrategyCandidate("pullback_in_trend", {"lookback": 30})
    rows = task15._candidate_rows(
        selection_state,
        [
            (champion, [0.30] * 6, 0.25),
            (challenger, [0.20] * 6, 0.15),
        ],
    )
    decision = inner_selection.select_candidate(
        selection_state["training_window"],
        task15._synthetic_config(selection_state, rows),
    )
    selected = decision.to_dict()["selected_candidate"]
    assert selected["canonical_candidate_id"] == rows[0].canonical_candidate_id
    current_origin = {
        "selection_decision": decision.to_dict(),
        "frozen_candidate_bundle": {
            "router_decision": {"outcome": "SPECIALIST"},
            "research_simulation_routable": True,
            "bundle_sha256": "b" * 64,
        },
    }

    def predecessor(candidate: StrategyCandidate):
        return {
            "bundle_sha256": "a" * 64,
            "specialist_bundle": {
                "base_candidate": {
                    "family": candidate.family,
                    "params": dict(candidate.params),
                }
            },
        }

    champion_choice = current_refit._pairwise_decision(
        predecessor(champion), current_origin
    )
    assert champion_choice["choice"] == current_refit.CHAMPION
    assert champion_choice["winner_candidate_id"] == rows[0].canonical_candidate_id

    challenger_choice = current_refit._pairwise_decision(
        predecessor(challenger), current_origin
    )
    assert challenger_choice["choice"] == current_refit.CHALLENGER
    assert challenger_choice["winner_candidate_id"] == rows[0].canonical_candidate_id

    with pytest.raises(current_refit.CurrentRefitError, match="retest"):
        current_refit._pairwise_decision(predecessor(missing), current_origin)


def test_rehashed_choice_feedback_freshness_or_activation_tampering_fails(state) -> None:
    *_, report = state
    for field, value, pattern in (
        ("outer_or_hindsight_feedback_used", True, "feedback|scope"),
        ("freshness", "FRESH", "freshness|scope"),
        ("canonical_adoption_eligible", True, "scope|adoption"),
        ("manual_research_shadow_start_allowed", True, "scope|shadow"),
        ("bot_start_allowed", True, "scope|start"),
    ):
        changed = deepcopy(report.to_dict())
        changed[field] = value
        basis = dict(changed)
        basis.pop("report_sha256")
        forged = current_refit.CurrentRefitDecision(
            current_refit._canonical(basis), current_refit._digest(basis)
        )
        with pytest.raises(current_refit.CurrentRefitError, match=pattern):
            current_refit.validate_current_refit_decision(forged)

    choice = deepcopy(report.to_dict())
    choice["champion_challenger_cash_decision"]["choice"] = (
        current_refit.CHALLENGER
    )
    choice_basis = dict(choice)
    choice_basis.pop("report_sha256")
    forged_choice = current_refit.CurrentRefitDecision(
        current_refit._canonical(choice_basis),
        current_refit._digest(choice_basis),
    )
    with pytest.raises(current_refit.CurrentRefitError, match="manipulated"):
        current_refit.validate_current_refit_decision(forged_choice)


def test_wrong_predecessor_expired_bundle_and_wrong_window_fail_closed(state) -> None:
    (
        plan,
        current_plan,
        process,
        baseline,
        gate,
        diagnostics,
        request,
        requested,
        report,
    ) = state

    wrong_predecessor = deepcopy(report.to_dict())
    wrong_predecessor["identity_manifest"]["predecessor_bundle_sha256"] = "f" * 64
    wrong_predecessor["identity_manifest_sha256"] = current_refit._digest(
        wrong_predecessor["identity_manifest"]
    )
    wrong_predecessor_basis = dict(wrong_predecessor)
    wrong_predecessor_basis.pop("report_sha256")
    wrong_predecessor["report_sha256"] = current_refit._digest(
        wrong_predecessor_basis
    )
    with pytest.raises(current_refit.CurrentRefitError, match="exact source replay"):
        current_refit.validate_current_refit_decision(
            wrong_predecessor,
            historical_boundary_plan=plan,
            current_boundary_plan=current_plan,
            historical_outer_process=process,
            baseline_ledger=baseline,
            monthly_quality_report=gate,
            historical_diagnostics=diagnostics,
            current_request=request,
            requested_at_utc=requested,
        )

    expired = deepcopy(report.to_dict())
    expired["identity_manifest"]["valid_until_utc"] = "2026-07-08T00:00:00Z"
    expired["identity_manifest_sha256"] = current_refit._digest(
        expired["identity_manifest"]
    )
    expired_basis = dict(expired)
    expired_basis.pop("report_sha256")
    forged_expired = current_refit.CurrentRefitDecision(
        current_refit._canonical(expired_basis), current_refit._digest(expired_basis)
    )
    with pytest.raises(current_refit.CurrentRefitError, match="target and validity"):
        current_refit.validate_current_refit_decision(forged_expired)

    wrong_window = deepcopy(report.to_dict())
    wrong_window["current_origin"]["training_start_inclusive"] = "2024-07-09"
    origin_basis = dict(wrong_window["current_origin"])
    origin_basis.pop("origin_sha256")
    wrong_window["current_origin"]["origin_sha256"] = current_refit._digest(
        origin_basis
    )
    wrong_window["identity_manifest"]["training_start_inclusive"] = "2024-07-09"
    wrong_window["identity_manifest"]["current_origin_sha256"] = wrong_window[
        "current_origin"
    ]["origin_sha256"]
    wrong_window["identity_manifest_sha256"] = current_refit._digest(
        wrong_window["identity_manifest"]
    )
    wrong_window_basis = dict(wrong_window)
    wrong_window_basis.pop("report_sha256")
    forged_window = current_refit.CurrentRefitDecision(
        current_refit._canonical(wrong_window_basis),
        current_refit._digest(wrong_window_basis),
    )
    with pytest.raises(outer_origins.OuterOriginError, match="boundary"):
        current_refit.validate_current_refit_decision(forged_window)
