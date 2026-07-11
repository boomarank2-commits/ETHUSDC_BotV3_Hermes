[CmdletBinding()]
param(
    [string]$RawRoot = "C:\TradingBot\data\ETHUSDC_BotV3_Hermes",
    [string]$ReportsRoot = "",
    [ValidateRange(1, 8)]
    [int]$MaxCycles = 8
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$ArgumentList,
        [string]$Description = $FilePath
    )

    Write-Host "==> $Description"
    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE"
    }
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

if (-not (Test-Path (Join-Path $RepoRoot "pyproject.toml") -PathType Leaf)) {
    throw "Repository root is invalid: pyproject.toml is missing"
}
if (-not (Test-Path (Join-Path $RepoRoot "src\ethusdc_bot") -PathType Container)) {
    throw "Repository root is invalid: src\ethusdc_bot is missing"
}
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python launcher 'py' is not available"
}

$GitStatus = (& git status --porcelain) -join "`n"
if ($LASTEXITCODE -ne 0) {
    throw "Could not read Git status"
}
if ($GitStatus.Trim().Length -ne 0) {
    throw "Working tree must be clean before a reproducible production research run"
}

$GitCommit = (& git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $GitCommit.Length -ne 40) {
    throw "Could not resolve the exact Git commit"
}
$GitBranch = (& git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or -not $GitBranch) {
    throw "Could not resolve the current Git branch"
}

$RawRootFull = [System.IO.Path]::GetFullPath($RawRoot)
$RepoRootFull = [System.IO.Path]::GetFullPath($RepoRoot)
if ($RawRootFull.Equals($RepoRootFull, [System.StringComparison]::OrdinalIgnoreCase) -or
    $RawRootFull.StartsWith($RepoRootFull.TrimEnd('\') + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Raw market data must remain outside the Git repository"
}
$EthFolder = Join-Path $RawRootFull "raw\binance\spot\ETHUSDC\klines\1m"
if (-not (Test-Path $EthFolder -PathType Container)) {
    throw "ETHUSDC 1m data folder is missing: $EthFolder"
}
$ZipCount = @(Get-ChildItem -Path $EthFolder -Filter "ETHUSDC-1m-*.zip" -File).Count
$ChecksumCount = @(Get-ChildItem -Path $EthFolder -Filter "ETHUSDC-1m-*.zip.CHECKSUM" -File).Count
if ($ZipCount -lt 1095 -or $ChecksumCount -lt 1095) {
    throw "Production research requires at least 1095 ETHUSDC ZIP/CHECKSUM day pairs; found ZIP=$ZipCount CHECKSUM=$ChecksumCount"
}

if (-not $ReportsRoot) {
    $ReportsRoot = Join-Path $RepoRoot "reports\research_loop"
}
$ReportsRootFull = [System.IO.Path]::GetFullPath($ReportsRoot)
New-Item -Path $ReportsRootFull -ItemType Directory -Force | Out-Null

$StartedAtUtc = [DateTime]::UtcNow
$Timestamp = $StartedAtUtc.ToString("yyyyMMddTHHmmssZ")
$ConsoleLog = Join-Path $ReportsRootFull "production_research_$Timestamp.console.log"

Invoke-Checked -FilePath "py" -ArgumentList @("-3.12", "-m", "pytest", "-q") -Description "Full Python test suite"
Invoke-Checked -FilePath "py" -ArgumentList @("-3.12", "-m", "compileall", "-q", "src") -Description "Python source compilation"

$ResearchArguments = @(
    "-3.12",
    "-m",
    "ethusdc_bot.backtest.research_loop_runner",
    "--raw-root", $RawRootFull,
    "--reports-root", $ReportsRootFull,
    "--max-cycles", "$MaxCycles",
    "--max-candidates-per-cycle", "40",
    "--tested-candidates-per-cycle", "12",
    "--walk-forward-candidates-per-cycle", "3",
    "--finalists-per-cycle", "2",
    "--walk-forward-folds", "6",
    "--rolling-origin-limit", "3"
)

Write-Host "==> Production Research Protocol v2"
Write-Host "Branch: $GitBranch"
Write-Host "Commit: $GitCommit"
Write-Host "Raw root: $RawRootFull"
Write-Host "Reports root: $ReportsRootFull"
Write-Host "Max cycles: $MaxCycles"

$ResearchOutput = & py @ResearchArguments 2>&1 | Tee-Object -FilePath $ConsoleLog
if ($LASTEXITCODE -ne 0) {
    throw "Production research failed with exit code $LASTEXITCODE. Console log: $ConsoleLog"
}

$ReportLine = $ResearchOutput | Where-Object { "$_" -match '^Report JSON:\s+(.+)$' } | Select-Object -Last 1
if (-not $ReportLine -or "$ReportLine" -notmatch '^Report JSON:\s+(.+)$') {
    throw "Research completed without reporting a JSON path. Console log: $ConsoleLog"
}
$ReportJson = $Matches[1].Trim()
if (-not [System.IO.Path]::IsPathRooted($ReportJson)) {
    $ReportJson = Join-Path $RepoRoot $ReportJson
}
$ReportJson = [System.IO.Path]::GetFullPath($ReportJson)
if (-not (Test-Path $ReportJson -PathType Leaf)) {
    throw "Reported JSON does not exist: $ReportJson"
}

$Report = Get-Content -Path $ReportJson -Raw -Encoding UTF8 | ConvertFrom-Json -Depth 100
if ($Report.execution_profile -ne "production_protocol") {
    throw "Unexpected execution profile: $($Report.execution_profile)"
}
if ($Report.audit_policy.evaluated_in_research_loop -ne $false) {
    throw "Safety violation: research loop evaluated an audit window"
}
if ($Report.window_plan.final_holdout_window.evaluated -ne $false) {
    throw "Safety violation: final holdout was evaluated"
}
if ($Report.safety_status.live -ne "locked" -or
    $Report.safety_status.paper -ne "locked" -or
    $Report.safety_status.testtrade -ne "locked" -or
    $Report.safety_status.orders -ne "disabled" -or
    $Report.safety_status.trading_api -ne "disabled" -or
    $Report.safety_status.api_keys -ne "not_used") {
    throw "Safety declaration in the research report is not canonical"
}

$LastCycle = $Report.cycles | Select-Object -Last 1
$Manifest = [ordered]@{
    schema_version = 1
    run_kind = "production_selection_research"
    started_at_utc = $StartedAtUtc.ToString("o")
    completed_at_utc = [DateTime]::UtcNow.ToString("o")
    git_branch = $GitBranch
    git_commit = $GitCommit
    working_tree_clean = $true
    raw_root = $RawRootFull
    reports_root = $ReportsRootFull
    max_cycles = $MaxCycles
    canonical_stage_budgets = [ordered]@{
        generated = 40
        tested = 12
        walk_forward = 3
        finalists = 2
    }
    report_json = $ReportJson
    console_log = $ConsoleLog
    loop_run_id = $Report.loop_run_id
    cycles_executed = $Report.cycles_executed
    stop_reason = $Report.stop_reason
    freeze_status = $Report.freeze_status
    final_holdout_evaluated = $false
    live_enabled = $false
    paper_enabled = $false
    testtrade_enabled = $false
    orders_enabled = $false
}
$ManifestPath = Join-Path $ReportsRootFull "production_research_$Timestamp.manifest.json"
$Manifest | ConvertTo-Json -Depth 10 | Set-Content -Path $ManifestPath -Encoding UTF8

Write-Host ""
Write-Host "=== Production Research Summary ==="
Write-Host "Run ID: $($Report.loop_run_id)"
Write-Host "Cycles: $($Report.cycles_executed)"
Write-Host "Stop reason: $($Report.stop_reason)"
Write-Host "Freeze status: $($Report.freeze_status)"
Write-Host "Best validation: $($Report.best_validation_result)"
if ($null -ne $LastCycle) {
    Write-Host "Last frontier: generated=$($LastCycle.generated_candidates) tested=$($LastCycle.tested_candidates) WFV=$($LastCycle.walk_forward_candidates) finalists=$($LastCycle.finalists)"
    Write-Host "Qualified finalists: $($LastCycle.qualified_finalists)"
}
Write-Host "Final holdout evaluated: False"
Write-Host "Live/Paper/Testtrade/Orders: locked"
Write-Host "Report JSON: $ReportJson"
Write-Host "Manifest: $ManifestPath"
Write-Host "Console log: $ConsoleLog"
