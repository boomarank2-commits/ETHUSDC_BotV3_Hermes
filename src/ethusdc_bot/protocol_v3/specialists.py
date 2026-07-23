"""Bounded local-specialist adapters over the existing simulator (Task 21)."""

from __future__ import annotations
from collections.abc import Mapping
from dataclasses import dataclass
import hashlib, json
from pathlib import Path
from typing import Any, Final

from ethusdc_bot.backtest.simulator import StrategyCandidate
from .feature_store import MultiTimeframeFeatureStore, validate_feature_store
from .opportunity_regime import COMPLETE, OpportunityRegimeAssessment

PROTOCOL_VERSION: Final = "3.0.0"
CONTRACT_PATH: Final = Path("configs/protocol_v3_specialists_contract.json")
CONTRACT_SCHEMA_VERSION: Final = "protocol_v3_specialists_contract_v1"
CONTRACT_VERSION: Final = "protocol_v3_bounded_local_specialists_v1"
BUNDLE_SCHEMA_VERSION: Final = "protocol_v3_specialist_candidate_bundle_v1"
GATE_SCHEMA_VERSION: Final = "protocol_v3_specialist_confirmation_v1"
NO_TRADE: Final = "no_trade"
SPECS: Final = {
    "trend_pullback_reclaim": ("pullback_in_trend", "TREND", "closed_15m_pullback_then_reclaim", 60, 720),
    "compression_breakout_retest": ("breakout_volatility_filter", "COMPRESSION", "closed_15m_breakout_then_held_retest", 60, 720),
    "range_reversion_confirmed": ("mean_reversion_regime_filter", "RANGE", "closed_15m_range_reentry", 15, 240),
    "multiday_swing_trend": ("momentum_trend_filter", "TREND", "closed_1d_and_4h_trend_alignment", 1440, 10080),
}
_SAFETY = {"api_keys":"forbidden","live":"locked","orders":"locked","paper":"locked","testtrade":"locked","trading_api":"forbidden","long_only":True,"symbol":"ETHUSDC","may_create_signal":False}
_CANONICAL = {"schema_version":CONTRACT_SCHEMA_VERSION,"protocol_version":PROTOCOL_VERSION,"contract_version":CONTRACT_VERSION,"specialists":[{"id":key,"base_family":value[0],"required_structure":value[1],"confirmation":value[2]} for key,value in SPECS.items()]+[{"id":"no_trade","base_family":None,"required_structure":None,"confirmation":"always_block"}],"engine_policy":{"reuse_existing_simulator":True,"second_simulation_engine_forbidden":True,"task20_assessment_must_be_prevalidated":True,"specialist_gate_may_confirm_existing_raw_signal_only":True,"specialist_gate_may_create_signal":False},"bounds":{f"{key}_max_hold_minutes":[value[3],value[4]] for key,value in SPECS.items()},"deferred_scope":{"router_task":22,"outer_orchestration_task":23},"safety":_SAFETY}

class SpecialistError(ValueError): pass

@dataclass(frozen=True)
class SpecialistCandidateBundle:
    specialist_id: str
    base_candidate: StrategyCandidate | None
    canonical_json: str
    bundle_sha256: str
    def to_dict(self)->dict[str,Any]:
        value=json.loads(self.canonical_json); value["bundle_sha256"]=self.bundle_sha256; return value

def load_specialists_contract(repo_root:str|Path)->dict[str,Any]:
    path=Path(repo_root).resolve(strict=True)/CONTRACT_PATH
    try: value=json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc: raise SpecialistError("specialists contract is missing or invalid") from exc
    if value != _CANONICAL: raise SpecialistError("Protocol v3 specialists contract is not canonical")
    return value

def build_specialist_bundle(specialist_id:str, base_candidate:StrategyCandidate|None)->SpecialistCandidateBundle:
    if specialist_id==NO_TRADE:
        if base_candidate is not None: raise SpecialistError("no_trade may not wrap a candidate")
        basis=_basis(specialist_id,None)
        return SpecialistCandidateBundle(specialist_id,None,_canonical(basis),_digest(basis))
    if specialist_id not in SPECS or not isinstance(base_candidate,StrategyCandidate): raise SpecialistError("specialist or base candidate is invalid")
    family,_,_,minimum,maximum=SPECS[specialist_id]
    if base_candidate.family != family: raise SpecialistError("specialist base family mismatch")
    params=dict(base_candidate.params)
    if params.get("symbol","ETHUSDC")!="ETHUSDC" or params.get("side","LONG")!="LONG": raise SpecialistError("specialists are ETHUSDC LONG-only")
    hold=params.get("max_hold_minutes")
    if type(hold) is not int or not minimum<=hold<=maximum: raise SpecialistError("specialist max_hold_minutes is outside frozen bounds")
    basis=_basis(specialist_id,base_candidate)
    return SpecialistCandidateBundle(specialist_id,base_candidate,_canonical(basis),_digest(basis))

def validate_specialist_bundle(bundle:SpecialistCandidateBundle)->SpecialistCandidateBundle:
    if not isinstance(bundle,SpecialistCandidateBundle): raise SpecialistError("verified specialist bundle required")
    expected=build_specialist_bundle(bundle.specialist_id,bundle.base_candidate)
    if bundle.to_dict()!=expected.to_dict(): raise SpecialistError("specialist bundle identity mismatch")
    return bundle

def evaluate_specialist_confirmation(bundle:SpecialistCandidateBundle,store:MultiTimeframeFeatureStore|Mapping[str,Any],assessment:OpportunityRegimeAssessment|Mapping[str,Any],*,context_timestamp_ms:int,raw_signal:bool)->dict[str,Any]:
    bundle=validate_specialist_bundle(bundle); feature_store=validate_feature_store(store).to_dict()
    if not isinstance(assessment,OpportunityRegimeAssessment): raise SpecialistError("verified Task-20 assessment required")
    if type(raw_signal) is not bool or type(context_timestamp_ms) is not int or context_timestamp_ms%60000: raise SpecialistError("specialist gate inputs are invalid")
    if context_timestamp_ms>feature_store["common_context_timestamp_ms"]: raise SpecialistError("specialist gate requests future features")
    regime=assessment.to_dict()
    if regime.get("state")!=COMPLETE or regime.get("context_timestamp_ms")!=context_timestamp_ms: return _gate(bundle,context_timestamp_ms,raw_signal,False,"regime_evidence_missing_or_stale")
    if bundle.specialist_id==NO_TRADE: return _gate(bundle,context_timestamp_ms,raw_signal,False,"no_trade_specialist")
    required=SPECS[bundle.specialist_id][1]
    if regime.get("structure")!=required or regime.get("routing_allowed") is not True: return _gate(bundle,context_timestamp_ms,raw_signal,False,"specialist_regime_mismatch")
    if not raw_signal: return _gate(bundle,context_timestamp_ms,False,False,"base_engine_raw_signal_absent")
    rows=[row for row in feature_store["series"]["ETHUSDC"]["15m"] if row["close_time_exclusive_ms"]<=context_timestamp_ms]
    daily=[row for row in feature_store["series"]["ETHUSDC"]["1d"] if row["close_time_exclusive_ms"]<=context_timestamp_ms]
    four=[row for row in feature_store["series"]["ETHUSDC"]["4h"] if row["close_time_exclusive_ms"]<=context_timestamp_ms]
    confirmed=False
    if bundle.specialist_id=="trend_pullback_reclaim" and len(rows)>=3: confirmed=rows[-2]["close"]<rows[-3]["close"] and rows[-1]["close"]>rows[-2]["high"]
    elif bundle.specialist_id=="compression_breakout_retest" and len(rows)>=22:
        level=max(row["high"] for row in rows[-22:-2]); confirmed=rows[-2]["close"]>level and rows[-1]["low"]<=level and rows[-1]["close"]>=level
    elif bundle.specialist_id=="range_reversion_confirmed" and len(rows)>=22:
        low=min(row["low"] for row in rows[-22:-2]); confirmed=rows[-2]["close"]<low and rows[-1]["close"]>low
    elif bundle.specialist_id=="multiday_swing_trend" and len(daily)>=3 and len(four)>=2: confirmed=daily[-1]["close"]>daily[-3]["close"] and four[-1]["close"]>four[-2]["close"]
    return _gate(bundle,context_timestamp_ms,True,confirmed,"specialist_confirmation_passed" if confirmed else "specialist_confirmation_absent")

def _basis(identifier:str,candidate:StrategyCandidate|None)->dict[str,Any]: return {"schema_version":BUNDLE_SCHEMA_VERSION,"protocol_version":PROTOCOL_VERSION,"contract_version":CONTRACT_VERSION,"specialist_id":identifier,"base_candidate":None if candidate is None else {"family":candidate.family,"params":dict(candidate.params)},"uses_existing_simulator":True,"safety":_SAFETY}
def _gate(bundle:SpecialistCandidateBundle,timestamp:int,raw:bool,allowed:bool,reason:str)->dict[str,Any]:
    basis={"schema_version":GATE_SCHEMA_VERSION,"bundle_sha256":bundle.bundle_sha256,"context_timestamp_ms":timestamp,"raw_signal":raw,"allowed":allowed and raw,"reason":reason,"may_create_signal":False,"safety":_SAFETY}; return {**basis,"gate_sha256":_digest(basis)}
def _canonical(value:Any)->str:return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False)
def _digest(value:Any)->str:return hashlib.sha256(_canonical(value).encode()).hexdigest()
__all__=["BUNDLE_SCHEMA_VERSION","CONTRACT_PATH","CONTRACT_SCHEMA_VERSION","CONTRACT_VERSION","GATE_SCHEMA_VERSION","NO_TRADE","SPECS","SpecialistCandidateBundle","SpecialistError","build_specialist_bundle","evaluate_specialist_confirmation","load_specialists_contract","validate_specialist_bundle"]
