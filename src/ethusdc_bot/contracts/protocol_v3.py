"""Fail-closed validation for the versioned Protocol v3 repository contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "protocol_v3_contract_manifest_v1"
PROTOCOL_VERSION = "3.0.0"
CONTRACT_GENERATION = "monthly_refit_pipeline_v3"
MANIFEST_PATH = Path("configs/protocol_v3_contract.json")
CANONICAL_DOCUMENT = Path("docs/42_PROTOCOL_V3_EXECUTABLE_CONTRACT.md")
REQUIRED_DOCUMENTS = (
    Path("AGENTS.md"),
    Path("PROJECT_CONTRACT.md"),
    Path("docs/31_PORTFOLIO_SHADOW_PRODUCT_CONTRACT.md"),
    CANONICAL_DOCUMENT,
)
VERSION_MARKER = "Protocol-v3-Vertragsgeneration: `3.0.0`"
MANIFEST_MARKER = "configs/protocol_v3_contract.json"


class ContractValidationError(ValueError):
    """Raised when the repository contract is missing or contradictory."""


def load_protocol_v3_contract(path: str | Path) -> dict[str, Any]:
    """Load and validate one Protocol v3 manifest from disk."""

    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractValidationError(f"Protocol v3 manifest missing: {source}") from exc
    except json.JSONDecodeError as exc:
        raise ContractValidationError(f"Protocol v3 manifest is not valid JSON: {source}") from exc
    if not isinstance(payload, dict):
        raise ContractValidationError("Protocol v3 manifest root must be an object")
    validate_protocol_v3_contract(payload)
    return payload


def validate_protocol_v3_contract(payload: Mapping[str, Any]) -> None:
    """Reject missing versions and cross-field contradictions fail-closed."""

    _expect(payload, "schema_version", SCHEMA_VERSION)
    _expect(payload, "protocol_version", PROTOCOL_VERSION)
    _expect(payload, "contract_generation", CONTRACT_GENERATION)
    _expect(payload, "protocol_status", "executable_contract")
    _expect(payload, "canonical_contract_document", CANONICAL_DOCUMENT.as_posix())
    _expect(payload, "champion_type", "monthly_refit_selection_pipeline")

    market = _mapping(payload, "market")
    _expect(market, "trade_symbol", "ETHUSDC", prefix="market")
    _expect(market, "venue", "binance_spot", prefix="market")
    _expect(market, "side", "LONG", prefix="market")
    _expect(market, "context_symbols", ["BTCUSDC", "ETHBTC"], prefix="market")
    _expect_false(market, "context_may_trade", prefix="market")
    _expect_false(market, "shorts_margin_futures_leverage", prefix="market")

    monthly = _mapping(payload, "monthly_process")
    _expect(monthly, "training_days_per_origin", 730, prefix="monthly_process")
    _expect(monthly, "process_oos_days", 365, prefix="monthly_process")
    _expect(monthly, "outer_origins", 12, prefix="monthly_process")
    _expect(monthly, "activation_delay_hours", 24, prefix="monthly_process")
    _expect(monthly, "monthly_process_oos_freshness", "NOT_FRESH", prefix="monthly_process")
    _expect_false(
        monthly,
        "monthly_process_oos_canonical_adoption_eligible",
        prefix="monthly_process",
    )

    consumed = _mapping(payload, "consumed_audit")
    _expect(consumed, "start_day", "2025-07-08", prefix="consumed_audit")
    _expect(consumed, "end_day_inclusive", "2026-07-07", prefix="consumed_audit")
    _expect(consumed, "status", "CONSUMED", prefix="consumed_audit")
    _expect(consumed, "freshness", "NOT_FRESH", prefix="consumed_audit")
    _expect_true(
        consumed,
        "raw_market_observations_may_enter_later_causal_training",
        prefix="consumed_audit",
    )
    for key in (
        "prior_pnl_may_enter_later_training",
        "prior_rankings_may_enter_later_training",
        "prior_reports_may_enter_later_training",
        "human_result_feedback_may_enter_later_training",
    ):
        _expect_false(consumed, key, prefix="consumed_audit")
    _expect(
        consumed,
        "historical_protocol_v3_process_status",
        "diagnostic_only",
        prefix="consumed_audit",
    )

    evidence = _mapping(payload, "evidence_classes")
    process_oos = _mapping(evidence, "monthly_process_oos", prefix="evidence_classes")
    _expect(process_oos, "freshness", "NOT_FRESH", prefix="evidence_classes.monthly_process_oos")
    _expect_false(
        process_oos,
        "canonical_final_evidence",
        prefix="evidence_classes.monthly_process_oos",
    )
    _expect_false(
        process_oos,
        "canonical_adoption_eligible",
        prefix="evidence_classes.monthly_process_oos",
    )

    sealed = _mapping(evidence, "sealed_final_holdout", prefix="evidence_classes")
    _expect(
        sealed,
        "freshness",
        "FRESH_ONLY_IF_PREREGISTERED_AND_UNSEEN",
        prefix="evidence_classes.sealed_final_holdout",
    )
    _expect_true(
        sealed,
        "canonical_final_evidence",
        prefix="evidence_classes.sealed_final_holdout",
    )
    _expect_true(
        sealed,
        "requires_pipeline_final_evaluator",
        prefix="evidence_classes.sealed_final_holdout",
    )

    forward = _mapping(evidence, "forward_shadow_month", prefix="evidence_classes")
    _expect(
        forward,
        "freshness",
        "FRESH_FORWARD_OBSERVATION",
        prefix="evidence_classes.forward_shadow_month",
    )
    _expect_false(
        forward,
        "canonical_final_evidence",
        prefix="evidence_classes.forward_shadow_month",
    )
    _expect_false(forward, "may_be_backfilled", prefix="evidence_classes.forward_shadow_month")

    challenger = _mapping(evidence, "research_challenger_shadow", prefix="evidence_classes")
    for key in ("orders", "trading_api", "canonical_adoption_eligible", "paper_testtrade_live_eligible"):
        _expect_false(challenger, key, prefix="evidence_classes.research_challenger_shadow")
    _expect_true(
        challenger,
        "requires_manual_user_action",
        prefix="evidence_classes.research_challenger_shadow",
    )
    _mapping(evidence, "diagnostic_only", prefix="evidence_classes")

    legacy = _mapping(payload, "legacy_separation")
    _expect_true(legacy, "protocol_v2_preserved", prefix="legacy_separation")
    _expect_true(legacy, "single_candidate_final_path_preserved", prefix="legacy_separation")
    _expect_false(
        legacy,
        "single_candidate_final_path_may_emit_protocol_v3_final",
        prefix="legacy_separation",
    )
    _expect_false(
        legacy,
        "protocol_v2_report_may_emit_protocol_v3_final",
        prefix="legacy_separation",
    )

    target = _mapping(payload, "target_policy")
    _expect(target, "target_usdc_per_calendar_day", 3.0, prefix="target_policy")
    _expect_true(target, "target_is_acceptance_metric", prefix="target_policy")
    _expect_false(target, "target_is_search_loss", prefix="target_policy")
    _expect_false(target, "search_may_stop_on_first_target_hit", prefix="target_policy")

    safety = _mapping(payload, "safety")
    for key in ("orders", "paper", "testtrade", "live"):
        _expect(safety, key, "locked", prefix="safety")
    for key in ("trading_api", "api_keys"):
        _expect(safety, key, "forbidden", prefix="safety")


def validate_repository_contracts(repo_root: str | Path) -> dict[str, Any]:
    """Validate the manifest and required version markers in governing documents."""

    root = Path(repo_root)
    payload = load_protocol_v3_contract(root / MANIFEST_PATH)
    for relative_path in REQUIRED_DOCUMENTS:
        path = root / relative_path
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise ContractValidationError(f"Required contract document missing: {relative_path}") from exc
        if VERSION_MARKER not in text:
            raise ContractValidationError(
                f"Required Protocol v3 version marker missing from {relative_path}"
            )
        if MANIFEST_MARKER not in text:
            raise ContractValidationError(
                f"Required Protocol v3 manifest reference missing from {relative_path}"
            )
    return payload


def _mapping(
    payload: Mapping[str, Any],
    key: str,
    *,
    prefix: str = "",
) -> Mapping[str, Any]:
    path = f"{prefix}.{key}" if prefix else key
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"Required object missing or invalid: {path}")
    return value


def _expect(
    payload: Mapping[str, Any],
    key: str,
    expected: Any,
    *,
    prefix: str = "",
) -> None:
    path = f"{prefix}.{key}" if prefix else key
    if key not in payload:
        raise ContractValidationError(f"Required contract field missing: {path}")
    actual = payload[key]
    if actual != expected:
        raise ContractValidationError(
            f"Contradictory contract field {path}: expected {expected!r}, got {actual!r}"
        )


def _expect_true(payload: Mapping[str, Any], key: str, *, prefix: str = "") -> None:
    _expect(payload, key, True, prefix=prefix)


def _expect_false(payload: Mapping[str, Any], key: str, *, prefix: str = "") -> None:
    _expect(payload, key, False, prefix=prefix)


__all__ = [
    "CANONICAL_DOCUMENT",
    "CONTRACT_GENERATION",
    "ContractValidationError",
    "MANIFEST_PATH",
    "PROTOCOL_VERSION",
    "SCHEMA_VERSION",
    "load_protocol_v3_contract",
    "validate_protocol_v3_contract",
    "validate_repository_contracts",
]
