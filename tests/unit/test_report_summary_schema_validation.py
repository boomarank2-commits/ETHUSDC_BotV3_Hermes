"""Strict schema validation tests for report summary placeholders."""

from pathlib import Path
import json

import pytest

from ethusdc_bot.reports.schema import validate_report_summary_placeholder
from ethusdc_bot.validation import SchemaValidationError


ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_REPORT_FIELDS = [
    "profit_usdc",
    "net_usdc_per_day",
    "winrate",
    "profit_factor",
    "best_candidate",
    "adopted_candidate",
    "trades",
    "trade_count",
    "real_trades",
    "engine_entry_attempts",
]


def load_report_summary():
    return json.loads((ROOT / "tests/fixtures/example_report_summary.json").read_text(encoding="utf-8"))


def assert_rejected(summary):
    with pytest.raises(SchemaValidationError):
        validate_report_summary_placeholder(summary)


def test_example_report_summary_placeholder_passes_strict_schema_validation():
    validate_report_summary_placeholder(load_report_summary())


@pytest.mark.parametrize("success_status", ["success", "passed", "profitable", "candidate_ready"])
def test_report_summary_placeholder_rejects_success_statuses(success_status):
    summary = load_report_summary()
    summary["status"] = success_status

    assert_rejected(summary)


def test_report_summary_placeholder_rejects_candidate_adoptable_true():
    summary = load_report_summary()
    summary["candidate_adoptable"] = True

    assert_rejected(summary)


@pytest.mark.parametrize("field_name", FORBIDDEN_REPORT_FIELDS)
def test_report_summary_placeholder_rejects_profit_candidate_and_trade_fields(field_name):
    summary = load_report_summary()
    summary[field_name] = 0

    assert_rejected(summary)


@pytest.mark.parametrize("bad_reason", ["", "   ", None])
def test_report_summary_placeholder_rejects_missing_or_empty_reason(bad_reason):
    summary = load_report_summary()
    summary["reason"] = bad_reason

    assert_rejected(summary)


def test_report_summary_placeholder_rejects_missing_required_fields():
    summary = load_report_summary()
    del summary["reason"]

    assert_rejected(summary)


def test_report_summary_placeholder_rejects_unknown_keys():
    summary = load_report_summary()
    summary["backtest_run_id"] = "fake-run"

    assert_rejected(summary)


@pytest.mark.parametrize(
    ("key", "bad_value"),
    [
        ("schema_version", "1"),
        ("template", "true"),
        ("status", 1),
        ("candidate_adoptable", "false"),
    ],
)
def test_report_summary_placeholder_rejects_wrong_types(key, bad_value):
    summary = load_report_summary()
    summary[key] = bad_value

    assert_rejected(summary)
