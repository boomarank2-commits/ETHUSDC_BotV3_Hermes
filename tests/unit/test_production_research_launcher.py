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
    assert r'raw\binance\spot\$Symbol\klines\1m' in text
    assert "Raw market data must remain outside the Git repository" in text


def test_launcher_refuses_dirty_worktree_and_binds_exact_commit() -> None:
    text = _script()

    assert "git status --porcelain" in text
    assert "Working tree must be clean" in text
    assert "git rev-parse HEAD" in text
    assert "git branch --show-current" in text
    assert "git_commit = $GitCommit" in text
    assert "working_tree_clean = $true" in text
    assert "production_research.active.lock" in text
    assert "[System.IO.FileShare]::None" in text
    assert "Another production research process already owns the run lock" in text
    assert "$RunLock.Dispose()" in text


def test_launcher_binds_src_layout_for_every_python_child_process() -> None:
    text = _script()

    assert '$SrcRoot = (Resolve-Path (Join-Path $RepoRoot "src")).Path' in text
    assert "$env:PYTHONPATH = $SrcRoot" in text
    assert '[System.IO.Path]::PathSeparator' in text
    assert "import ethusdc_bot.backtest.research_loop_runner" in text
    assert "import ethusdc_bot.backtest.research_supervisor" in text
    assert "RESEARCH_MODULE_IMPORT_OK" in text
    assert "source_root = $SrcRoot" in text
    assert "pythonpath = $env:PYTHONPATH" in text


def test_launcher_requires_complete_three_year_aligned_market_inventory() -> None:
    text = _script()

    assert "function Assert-SymbolInventory" in text
    assert '@("ETHUSDC", "BTCUSDC", "ETHBTC")' in text
    assert '"$Symbol-1m-*.zip"' in text
    assert '"$Symbol-1m-*.zip.CHECKSUM"' in text
    assert "$ZipCount -lt 1095" in text
    assert "$ChecksumCount -lt 1095" in text
    assert "Unpaired $Symbol ZIP detected" in text
    assert "Unpaired $Symbol CHECKSUM detected" in text
    assert "market_inventory = $MarketInventory" in text
    assert 'context_only_symbols = @("BTCUSDC", "ETHBTC")' in text
    assert '[string]$DataEndDay = "2026-07-07"' in text
    assert 'selected_end_day = $EndDay' in text
    assert '$Sorted[-1].Name -ne $CutoffName' in text
    assert "inventory does not end on the bound data day" in text


def test_launcher_runs_full_checks_before_supervised_research() -> None:
    text = _script()
    inventory_position = text.index("Assert-SymbolInventory -Symbol $Symbol")
    pytest_position = text.index('"pytest", "-q"')
    compile_position = text.index('"compileall", "-q", "src"')
    import_position = text.index("RESEARCH_MODULE_IMPORT_OK")
    research_position = text.index('"ethusdc_bot.backtest.research_supervisor"')

    assert inventory_position < pytest_position < research_position
    assert compile_position < research_position
    assert import_position < research_position
    assert 'Invoke-Checked -FilePath "py"' in text


def test_launcher_uses_exact_production_stage_budgets_and_context() -> None:
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
    assert '"--enable-context"' in text
    assert '"--data-end-day", $DataEndDay' in text
    assert '"--fixture-smoke"' not in text


def test_launcher_rejects_holdout_noncanonical_safety_or_missing_context_proof() -> None:
    text = _script()

    assert "context_research\\.enabled=true" in text
    assert "context_generated=6 context_tested=2" in text
    assert "walk_forward_folds=6 rolling_origin_limit=3" in text
    assert "audit_evaluated=false final_holdout_evaluated=false" in text
    assert "Every completed cycle must prove exact 40/12/3/2 stages" in text
    assert '"Holdout evaluated: False"' in text
    assert '"Consumed audit affects selection: False"' in text
    assert '"Live/Paper/Testtrade locked. No orders, no Trading API, no API keys."' in text


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


def test_launcher_never_deserializes_the_multi_gigabyte_detail_json() -> None:
    text = _script()

    assert "Get-Content -Path $ReportJson" not in text
    assert "ConvertFrom-Json" not in text
    assert "Get-Content -Path $ReportTxt" in text
    assert "Never deserialize the multi-GB" in text
