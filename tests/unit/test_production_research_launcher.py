"""Static safety and reproducibility checks for the Windows research launcher."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "run_production_research.ps1"


def _script() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_launcher_exists_and_targets_canonical_external_data_root() -> None:
    text = _script()

    assert SCRIPT.is_file()
    assert r'C:\TradingBot\data\ETHUSDC_BotV3_Hermes' in text
    assert r'raw\binance\spot\ETHUSDC\klines\1m' in text
    assert "Raw market data must remain outside the Git repository" in text


def test_launcher_refuses_dirty_worktree_and_binds_exact_commit() -> None:
    text = _script()

    assert "git status --porcelain" in text
    assert "Working tree must be clean" in text
    assert "git rev-parse HEAD" in text
    assert "git branch --show-current" in text
    assert "git_commit = $GitCommit" in text
    assert "working_tree_clean = $true" in text


def test_launcher_requires_complete_three_year_ethusdc_inventory() -> None:
    text = _script()

    assert '"ETHUSDC-1m-*.zip"' in text
    assert '"ETHUSDC-1m-*.zip.CHECKSUM"' in text
    assert "$ZipCount -lt 1095" in text
    assert "$ChecksumCount -lt 1095" in text
    assert "Unpaired ETHUSDC ZIP detected" in text


def test_launcher_runs_full_checks_before_research() -> None:
    text = _script()
    pytest_position = text.index('"pytest", "-q"')
    compile_position = text.index('"compileall", "-q", "src"')
    research_position = text.index('"ethusdc_bot.backtest.research_loop_runner"')

    assert pytest_position < research_position
    assert compile_position < research_position
    assert 'Invoke-Checked -FilePath "py"' in text


def test_launcher_uses_exact_production_stage_budgets() -> None:
    text = _script()

    expected_arguments = {
        "--max-candidates-per-cycle": "40",
        "--tested-candidates-per-cycle": "12",
        "--walk-forward-candidates-per-cycle": "3",
        "--finalists-per-cycle": "2",
        "--walk-forward-folds": "6",
        "--rolling-origin-limit": "3",
    }
    for argument, value in expected_arguments.items():
        assert f'"{argument}", "{value}"' in text
    assert '"--fixture-smoke"' not in text


def test_launcher_rejects_holdout_or_noncanonical_safety_report() -> None:
    text = _script()

    assert '$Report.audit_policy.evaluated_in_research_loop -ne $false' in text
    assert '$Report.window_plan.final_holdout_window.evaluated -ne $false' in text
    assert '$Report.safety_status.live -ne "locked"' in text
    assert '$Report.safety_status.paper -ne "locked"' in text
    assert '$Report.safety_status.testtrade -ne "locked"' in text
    assert '$Report.safety_status.orders -ne "not_created"' in text
    assert '$Report.safety_status.binance_trading_api -ne "not_used"' in text
    assert '$Report.safety_status.api_keys -ne "not_used"' in text
    assert '$Report.safety_status.short_margin_futures_leverage -ne "forbidden"' in text
    assert '$Report.safety_status.candidate_adoptable -ne $false' in text


def test_launcher_has_no_network_or_order_execution_commands() -> None:
    text = _script().lower()

    forbidden_commands = (
        "invoke-restmethod",
        "invoke-webrequest",
        "start-process",
        "curl ",
        "wget ",
        "create_order",
        "send_order",
        "/api/v3/order",
        "client_order_id",
    )
    for command in forbidden_commands:
        assert command not in text

    native_invocations = re.findall(r"(?m)^\s*&\s+([a-zA-Z0-9_.-]+)", text)
    assert set(native_invocations) <= {"$filepath", "git", "py"}


def test_launcher_writes_auditable_outputs_without_claiming_target_success() -> None:
    text = _script()

    assert "console.log" in text
    assert "manifest.json" in text
    assert "report_json = $ReportJson" in text
    assert "final_holdout_evaluated = $false" in text
    assert "orders_enabled = $false" in text
    assert "Final holdout evaluated: False" in text
    assert "3 USDC/Tag erreicht" not in text
    assert "+3 USDC/day target was reached" not in text


def test_launcher_remains_windows_powershell_51_compatible_for_json_reading() -> None:
    text = _script()

    assert "ConvertFrom-Json -Depth" not in text
    assert "| ConvertFrom-Json" in text
