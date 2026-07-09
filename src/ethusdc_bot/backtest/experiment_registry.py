"""Durable append-only registry for offline research experiments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExperimentPaths:
    json_path: Path
    txt_path: Path
    index_path: Path


def record_experiment(experiment: dict[str, Any], reports_root: str | Path = "reports/research") -> ExperimentPaths:
    root = Path(reports_root)
    root.mkdir(parents=True, exist_ok=True)
    run_id = str(experiment["run_id"])
    json_path = _unique_path(root / f"{run_id}.json")
    txt_path = json_path.with_suffix(".txt")
    stored = dict(experiment)
    stored["run_id"] = json_path.stem
    stored.setdefault("timestamp", datetime.now(UTC).isoformat().replace("+00:00", "Z"))
    stored.setdefault("report_links", {})
    stored["report_links"] = {**stored.get("report_links", {}), "json": str(json_path), "txt": str(txt_path)}
    json_path.write_text(json.dumps(stored, indent=2, sort_keys=True), encoding="utf-8")
    txt_path.write_text(format_experiment_text(stored), encoding="utf-8")
    index_path = root / "index.jsonl"
    with index_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_index_record(stored), sort_keys=True) + "\n")
    return ExperimentPaths(json_path=json_path, txt_path=txt_path, index_path=index_path)


def format_experiment_text(experiment: dict[str, Any]) -> str:
    blind = experiment.get("blindtest_metrics", {})
    validation = experiment.get("validation_metrics", {})
    training = experiment.get("training_metrics", {})
    target_line = "Ziel erreicht" if experiment.get("target_reached") else "Ziel nicht erreicht"
    return "\n".join(
        [
            "ETHUSDC Offline Research Experiment",
            f"Run-ID: {experiment.get('run_id')}",
            f"Git commit: {experiment.get('git_commit')}",
            f"Data window: {experiment.get('data_window')}",
            f"Training window: {experiment.get('training_window')}",
            f"Validation window: {experiment.get('validation_window')}",
            f"Blindtest window: {experiment.get('blindtest_window')}",
            f"Families: {experiment.get('strategy_families')}",
            f"Parameter counts: {experiment.get('parameter_counts')}",
            f"Selected candidate: {experiment.get('selected_candidate')}",
            f"Why selected: {experiment.get('why_selected')}",
            f"Training net_usdc_per_day: {training.get('net_usdc_per_day')}",
            f"Validation net_usdc_per_day: {validation.get('net_usdc_per_day')}",
            f"Blindtest net_usdc_per_day: {blind.get('net_usdc_per_day')}",
            f"Target: >= {experiment.get('target_usdc_per_day')} USDC/day",
            target_line,
            "Live/Paper/Testtrade locked. No orders, no Trading API, no API keys.",
            "",
        ]
    )


def _index_record(experiment: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": experiment.get("run_id"),
        "timestamp": experiment.get("timestamp"),
        "git_commit": experiment.get("git_commit"),
        "target_reached": experiment.get("target_reached"),
        "target_usdc_per_day": experiment.get("target_usdc_per_day"),
        "selected_candidate": experiment.get("selected_candidate"),
        "blindtest_net_usdc_per_day": experiment.get("blindtest_metrics", {}).get("net_usdc_per_day"),
        "json": experiment.get("report_links", {}).get("json"),
        "txt": experiment.get("report_links", {}).get("txt"),
    }


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(1, 10_000):
        candidate = path.with_name(f"{path.stem}_{index:03d}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError("could not allocate unique experiment path")
