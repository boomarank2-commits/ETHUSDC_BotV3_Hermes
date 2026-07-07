"""Config template tests for Phase 1.

These tests intentionally parse only simple TOML values via Python's standard tomllib.
"""

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_default_config_template_contains_required_project_limits():
    config_path = ROOT / "config" / "default.toml"
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))

    assert config["project"]["symbol"] == "ETHUSDC"
    assert config["project"]["quote_asset"] == "USDC"
    assert config["project"]["market_type"] == "spot"
    assert config["project"]["position_mode"] == "long_only"
    assert config["project"]["start_capital_usdc"] == 100
    assert config["data_requirements"]["training_days"] == 730
    assert config["data_requirements"]["blindtest_days"] == 365
    assert config["data_requirements"]["required_ethusdc_utc_days"] == 1095
    assert config["data_requirements"]["raw_data_location"] == "outside_repository"


def test_default_config_template_keeps_all_live_paths_disabled():
    config_path = ROOT / "config" / "default.toml"
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))

    assert config["safety"]["live_enabled"] is False
    assert config["safety"]["paper_enabled"] is False
    assert config["safety"]["testtrade_enabled"] is False
    assert config["safety"]["shorts_enabled"] is False
    assert config["safety"]["margin_enabled"] is False
    assert config["safety"]["futures_enabled"] is False
    assert config["safety"]["leverage_enabled"] is False
