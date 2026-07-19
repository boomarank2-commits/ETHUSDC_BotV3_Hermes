"""Exact deterministic CSCV/PBO evidence for Protocol-v3 Task 17."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
from itertools import combinations
import json
import math
from pathlib import Path
from typing import Any, Final

from .candidate_matrix import CandidateDailyMatrix, validate_candidate_daily_matrix

PROTOCOL_VERSION: Final = "3.0.0"
CONTRACT_PATH: Final = Path("configs/protocol_v3_pbo_contract.json")
CONTRACT_SCHEMA_VERSION: Final = "protocol_v3_pbo_contract_v1"
CONTRACT_VERSION: Final = "protocol_v3_exact_cscv_pbo_v1"
EVIDENCE_SCHEMA_VERSION: Final = "protocol_v3_pbo_evidence_v1"
IDENTITY_SCHEMA_VERSION: Final = "protocol_v3_pbo_identity_v1"
CASH_ID: Final = "protocol_v3_cash_no_trade_v1"
COMPLETE: Final = "COMPLETE"
INSUFFICIENT_EVIDENCE: Final = "INSUFFICIENT_EVIDENCE"
BLOCKS: Final = 12
DAYS_PER_BLOCK: Final = 30
IS_BLOCKS: Final = 6
SPLIT_COUNT: Final = 924
REQUIRED_DAYS: Final = 360
ZERO_HASH: Final = "0" * 64

_SAFETY = {
    "api_keys": "forbidden", "live": "locked", "orders": "locked",
    "paper": "locked", "testtrade": "locked", "trading_api": "forbidden",
}
_CANONICAL_CONTRACT = {
    "schema_version": CONTRACT_SCHEMA_VERSION, "protocol_version": PROTOCOL_VERSION,
    "contract_version": CONTRACT_VERSION, "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
    "identity_schema_version": IDENTITY_SCHEMA_VERSION, "cash_id": CASH_ID,
    "partition_policy": {"days": 360, "blocks": 12, "days_per_block": 30, "is_blocks": 6, "split_count": 924, "oos_is_exact_complement": True},
    "ranking_policy": {"is_metric": "mean_daily_net_mtm_usdc", "is_tie_primary": "canonical_candidate_id_ascending", "duplicate_candidate_tie_secondary": "canonical_profile_id_ascending", "oos_ties": "average_rank", "oos_rank_worst": 1, "cash_participates_in_is_and_oos": True, "no_rounding_before_decisions": True},
    "formula": {"omega": "(rank_minus_0.5)/M", "lambda": "ln(omega/(1-omega))", "pbo": "count(lambda<=0)/924", "maximum_release_pbo": 0.1, "trading_profile_must_strictly_beat_cash": True},
    "insufficient_evidence": {"minimum_trading_profiles": 2, "numeric_replacement_forbidden": True},
    "deferred_scope": {"dsr_task": 18, "outer_bootstrap_task": 27, "monthly_gate_task": 26},
    "safety": _SAFETY,
}


class PBOError(ValueError):
    """Raised for malformed or contradictory CSCV/PBO evidence."""


@dataclass(frozen=True)
class PBOEvidence:
    canonical_json: str
    evidence_sha256: str

    def to_dict(self) -> dict[str, Any]:
        payload = json.loads(self.canonical_json)
        payload["evidence_sha256"] = self.evidence_sha256
        return payload

    @property
    def identity_payload(self) -> dict[str, Any]:
        return build_pbo_identity_payload(self)


def load_pbo_contract(repo_root: str | Path) -> dict[str, Any]:
    path = Path(repo_root).resolve(strict=True) / CONTRACT_PATH
    try:
        payload = _strict_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PBOError("PBO contract is missing or invalid") from exc
    if payload != _CANONICAL_CONTRACT:
        raise PBOError("Protocol v3 PBO contract is not canonical")
    return payload


def calculate_pbo(matrix: CandidateDailyMatrix | Mapping[str, Any]) -> PBOEvidence:
    validated = validate_candidate_daily_matrix(matrix)
    basis = _pbo_basis(validated)
    return validate_pbo_evidence({**basis, "evidence_sha256": _digest(basis)})


def _pbo_basis(validated: CandidateDailyMatrix) -> dict[str, Any]:
    payload = validated.to_dict()
    profiles = sorted(
        (profile for cycle in payload["cycles"] for profile in cycle["profiles"]),
        key=lambda row: (row["candidate_id"], row["profile_id"]),
    )
    base = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION,
        "matrix_identity": validated.identity_payload,
        "cash_id": CASH_ID,
        "trading_profile_ids": [row["profile_id"] for row in profiles],
        "trading_candidate_ids": [row["candidate_id"] for row in profiles],
        "rank_universe_size": len(profiles) + 1,
        "day_count": REQUIRED_DAYS,
        "block_count": BLOCKS,
        "days_per_block": DAYS_PER_BLOCK,
        "safety": _SAFETY,
    }
    if len(profiles) < 2:
        basis = {
            **base,
            "state": INSUFFICIENT_EVIDENCE,
            "reason": "fewer_than_two_trading_profiles",
            "split_count": 0,
            "splits": [],
            "splits_sha256": ZERO_HASH,
            "negative_lambda_count": None,
            "development_pbo": None,
            "candidate_beats_cash": {},
            "aggregate_mean_daily_net_mtm_usdc": {},
        }
        return basis

    series = {row["profile_id"]: [float(item["net_usdc"]) for item in row["daily_net_mtm_usdc"]] for row in profiles}
    candidate_by_profile = {row["profile_id"]: row["candidate_id"] for row in profiles}
    columns = [*series, CASH_ID]
    split_rows: list[dict[str, Any]] = []
    negative = 0
    all_blocks = tuple(range(BLOCKS))
    for split_index, is_blocks in enumerate(combinations(all_blocks, IS_BLOCKS), start=1):
        is_set = set(is_blocks)
        oos_blocks = tuple(block for block in all_blocks if block not in is_set)
        is_days = _block_days(is_blocks)
        oos_days = _block_days(oos_blocks)
        is_means = {column: _mean(series[column], is_days) if column != CASH_ID else 0.0 for column in columns}
        winner = min(
            columns,
            key=lambda column: (-is_means[column], *_tie_key(column, candidate_by_profile)),
        )
        oos_means = {column: _mean(series[column], oos_days) if column != CASH_ID else 0.0 for column in columns}
        ranks = _average_ranks(oos_means)
        rank = ranks[winner]
        universe = len(columns)
        omega = (rank - 0.5) / universe
        logit = math.log(omega / (1.0 - omega))
        if logit <= 0.0:
            negative += 1
        split_rows.append({
            "split_index": split_index,
            "is_blocks": list(is_blocks),
            "oos_blocks": list(oos_blocks),
            "is_day_count": len(is_days),
            "oos_day_count": len(oos_days),
            "is_winner_profile_id": winner,
            "is_winner_candidate_id": CASH_ID if winner == CASH_ID else candidate_by_profile[winner],
            "is_winner_mean": is_means[winner],
            "oos_winner_mean": oos_means[winner],
            "oos_average_rank": rank,
            "omega": omega,
            "lambda": logit,
        })
    aggregate = {profile_id: math.fsum(values) / REQUIRED_DAYS for profile_id, values in series.items()}
    beats_cash = {profile_id: value > 0.0 for profile_id, value in aggregate.items()}
    basis = {
        **base,
        "state": COMPLETE,
        "reason": "complete_12_block_cscv",
        "split_count": len(split_rows),
        "splits": split_rows,
        "splits_sha256": _digest(split_rows),
        "negative_lambda_count": negative,
        "development_pbo": negative / SPLIT_COUNT,
        "candidate_beats_cash": beats_cash,
        "aggregate_mean_daily_net_mtm_usdc": aggregate,
    }
    return basis


def validate_pbo_evidence(value: PBOEvidence | Mapping[str, Any]) -> PBOEvidence:
    root = value.to_dict() if isinstance(value, PBOEvidence) else dict(_mapping(value, "pbo_evidence"))
    expected = {"schema_version", "protocol_version", "contract_version", "matrix_identity", "cash_id", "trading_profile_ids", "trading_candidate_ids", "rank_universe_size", "day_count", "block_count", "days_per_block", "state", "reason", "split_count", "splits", "splits_sha256", "negative_lambda_count", "development_pbo", "candidate_beats_cash", "aggregate_mean_daily_net_mtm_usdc", "safety", "evidence_sha256"}
    if set(root) != expected:
        raise PBOError("PBO evidence fields are missing or unexpected")
    if root["schema_version"] != EVIDENCE_SCHEMA_VERSION or root["protocol_version"] != PROTOCOL_VERSION or root["contract_version"] != CONTRACT_VERSION or root["cash_id"] != CASH_ID:
        raise PBOError("PBO evidence versions or cash identity are invalid")
    from .candidate_matrix import validate_candidate_matrix_identity_payload
    identity = validate_candidate_matrix_identity_payload(root["matrix_identity"])
    matrix = identity["matrix"]
    profiles = sorted((profile for cycle in matrix["cycles"] for profile in cycle["profiles"]), key=lambda row: (row["candidate_id"], row["profile_id"]))
    profile_ids = [row["profile_id"] for row in profiles]
    candidate_ids = [row["candidate_id"] for row in profiles]
    if root["trading_profile_ids"] != profile_ids or root["trading_candidate_ids"] != candidate_ids or root["rank_universe_size"] != len(profiles) + 1:
        raise PBOError("PBO inventory is not derived from the complete Task-16 matrix")
    if root["day_count"] != REQUIRED_DAYS or root["block_count"] != BLOCKS or root["days_per_block"] != DAYS_PER_BLOCK:
        raise PBOError("PBO partition dimensions are invalid")
    recomputed = _pbo_basis(validate_candidate_daily_matrix(matrix))
    for key in ("state", "reason", "split_count", "splits", "splits_sha256", "negative_lambda_count", "development_pbo", "candidate_beats_cash", "aggregate_mean_daily_net_mtm_usdc"):
        if root[key] != recomputed[key]:
            raise PBOError("PBO evidence differs from exact CSCV recomputation")
    if root["safety"] != _SAFETY:
        raise PBOError("PBO safety locks are invalid")
    observed = _sha(root["evidence_sha256"], "evidence_sha256")
    basis = dict(root); basis.pop("evidence_sha256")
    if observed != _digest(basis):
        raise PBOError("PBO evidence digest mismatch")
    return PBOEvidence(_canonical(basis), observed)


def build_pbo_identity_payload(evidence: PBOEvidence | Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_pbo_evidence(evidence)
    basis = {"identity_schema_version": IDENTITY_SCHEMA_VERSION, "evidence": validated.to_dict(), "evidence_sha256": validated.evidence_sha256}
    return {**basis, "identity_sha256": _digest(basis)}


def validate_pbo_identity_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    root = dict(_mapping(value, "pbo_identity"))
    if set(root) != {"identity_schema_version", "evidence", "evidence_sha256", "identity_sha256"} or root["identity_schema_version"] != IDENTITY_SCHEMA_VERSION:
        raise PBOError("PBO identity fields or version are invalid")
    evidence = validate_pbo_evidence(root["evidence"])
    expected = build_pbo_identity_payload(evidence)
    if root != expected:
        raise PBOError("PBO identity is not canonical")
    return expected


def _block_days(blocks: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(day for block in blocks for day in range(block * DAYS_PER_BLOCK, (block + 1) * DAYS_PER_BLOCK))


def _mean(values: list[float], indexes: tuple[int, ...]) -> float:
    return math.fsum(values[index] for index in indexes) / len(indexes)


def _tie_key(profile_id: str, candidate_by_profile: Mapping[str, str]) -> tuple[str, str]:
    return (CASH_ID, CASH_ID) if profile_id == CASH_ID else (candidate_by_profile[profile_id], profile_id)


def _average_ranks(scores: Mapping[str, float]) -> dict[str, float]:
    ordered = sorted(scores, key=lambda key: (scores[key], *_tie_key(key, {item: item for item in scores if item != CASH_ID})))
    ranks: dict[str, float] = {}
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and scores[ordered[end]] == scores[ordered[start]]:
            end += 1
        average = ((start + 1) + end) / 2.0
        for key in ordered[start:end]:
            ranks[key] = average
        start = end
    return ranks


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PBOError(f"{path} must be an object")
    return value


def _sha(value: Any, path: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise PBOError(f"{path} must be a lowercase SHA-256 digest")
    return value


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _strict_loads(text: str) -> dict[str, Any]:
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise PBOError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=hook, parse_constant=lambda value: (_ for _ in ()).throw(PBOError(f"non-finite JSON constant: {value}")))


__all__ = ["BLOCKS", "CASH_ID", "COMPLETE", "CONTRACT_PATH", "CONTRACT_SCHEMA_VERSION", "CONTRACT_VERSION", "DAYS_PER_BLOCK", "EVIDENCE_SCHEMA_VERSION", "IDENTITY_SCHEMA_VERSION", "INSUFFICIENT_EVIDENCE", "IS_BLOCKS", "PBOError", "PBOEvidence", "SPLIT_COUNT", "build_pbo_identity_payload", "calculate_pbo", "load_pbo_contract", "validate_pbo_evidence", "validate_pbo_identity_payload"]
