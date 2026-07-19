"""Task-28 tests for the current 730-day refit decision envelope."""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

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


def _current_request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, current_plan):
    base = task23.support.build_state(tmp_path / "current", monkeypatch)
    generation = pipeline.build_pipeline_generation(REPO_ROOT)
    manifest = build_pre_run_manifest(
        generation,
        current_plan,
        code_commit=task23.support.COMMIT,
    )
    origin = current_plan.origins[-1]
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


def test_late_or_wrong_anchor_refit_fails_closed(state) -> None:
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
    with pytest.raises(current_refit.CurrentRefitError, match=r"missed T\+24h"):
        current_refit.build_current_refit_decision(
            historical_boundary_plan=plan,
            current_boundary_plan=current_plan,
            historical_outer_process=process,
            baseline_ledger=baseline,
            monthly_quality_report=gate,
            historical_diagnostics=diagnostics,
            current_request=request,
            requested_at_utc=datetime(2026, 7, 9, 0, 0, 1, tzinfo=UTC),
        )
    wrong = boundaries.build_monthly_process_boundary_plan("2026-09-08")
    with pytest.raises(current_refit.CurrentRefitError, match="historical process end"):
        current_refit.build_current_refit_decision(
            historical_boundary_plan=plan,
            current_boundary_plan=wrong,
            historical_outer_process=process,
            baseline_ledger=baseline,
            monthly_quality_report=gate,
            historical_diagnostics=diagnostics,
            current_request=request,
            requested_at_utc=datetime(2026, 7, 8, tzinfo=UTC),
        )


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
