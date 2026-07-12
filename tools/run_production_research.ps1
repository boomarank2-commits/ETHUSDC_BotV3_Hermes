[CmdletBinding()]
param(
    [string]$RawRoot = "C:\TradingBot\data\ETHUSDC_BotV3_Hermes",
    [string]$ReportsRoot = "",
    [ValidateRange(1, 8)]
    [int]$MaxCycles = 8,
    [ValidatePattern('^\d{4}-\d{2}-\d{2}$')]
    [string]$DataEndDay = "2026-07-07"
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

function Assert-SymbolInventory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Symbol,
        [Parameter(Mandatory = $true)]
        [string]$Root,
        [Parameter(Mandatory = $true)]
        [string]$EndDay
    )

    $Folder = Join-Path $Root "raw\binance\spot\$Symbol\klines\1m"
    if (-not (Test-Path $Folder -PathType Container)) {
        throw "$Symbol 1m data folder is missing: $Folder"
    }
    $CutoffName = "$Symbol-1m-$EndDay.zip"
    $ZipFiles = @(
        Get-ChildItem -Path $Folder -Filter "$Symbol-1m-*.zip" -File |
            Where-Object { $_.Name -le $CutoffName }
    )
    $ChecksumFiles = @(
        Get-ChildItem -Path $Folder -Filter "$Symbol-1m-*.zip.CHECKSUM" -File |
            Where-Object {
                $TargetName = $_.Name.Substring(0, $_.Name.Length - ".CHECKSUM".Length)
                $TargetName -le $CutoffName
            }
    )
    $ZipCount = $ZipFiles.Count
    $ChecksumCount = $ChecksumFiles.Count
    if ($ZipCount -lt 1095 -or $ChecksumCount -lt 1095) {
        throw "Production context research requires at least 1095 $Symbol ZIP/CHECKSUM day pairs; found ZIP=$ZipCount CHECKSUM=$ChecksumCount"
    }

    $ZipNames = @{}
    foreach ($Zip in $ZipFiles) {
        $ZipNames[$Zip.Name] = $true
    }
    $ChecksumNames = @{}
    foreach ($Checksum in $ChecksumFiles) {
        $TargetName = $Checksum.Name.Substring(0, $Checksum.Name.Length - ".CHECKSUM".Length)
        $ChecksumNames[$TargetName] = $true
    }
    $UnpairedZip = $ZipFiles | Where-Object { -not $ChecksumNames.ContainsKey($_.Name) } | Select-Object -First 1
    if ($null -ne $UnpairedZip) {
        throw "Unpaired $Symbol ZIP detected: $($UnpairedZip.FullName)"
    }
    $UnpairedChecksum = $ChecksumFiles | Where-Object {
        $TargetName = $_.Name.Substring(0, $_.Name.Length - ".CHECKSUM".Length)
        -not $ZipNames.ContainsKey($TargetName)
    } | Select-Object -First 1
    if ($null -ne $UnpairedChecksum) {
        throw "Unpaired $Symbol CHECKSUM detected: $($UnpairedChecksum.FullName)"
    }

    $Sorted = @($ZipFiles | Sort-Object Name)
    if ($Sorted[-1].Name -ne $CutoffName) {
        throw "$Symbol inventory does not end on the bound data day $EndDay"
    }
    return [ordered]@{
        symbol = $Symbol
        folder = $Folder
        zip_count = $ZipCount
        checksum_count = $ChecksumCount
        paired_count = $ZipCount
        selected_end_day = $EndDay
        first_file = $Sorted[0].Name
        last_file = $Sorted[-1].Name
    }
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$SrcRoot = (Resolve-Path (Join-Path $RepoRoot "src")).Path
Set-Location $RepoRoot

if (-not (Test-Path (Join-Path $RepoRoot "pyproject.toml") -PathType Leaf)) {
    throw "Repository root is invalid: pyproject.toml is missing"
}
if (-not (Test-Path (Join-Path $SrcRoot "ethusdc_bot") -PathType Container)) {
    throw "Repository root is invalid: src\ethusdc_bot is missing"
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git is not available"
}
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python launcher 'py' is not available"
}

# The repository uses a src layout. Bind it explicitly for every child Python
# process so the long research invocation cannot depend on an editable install
# or on a shell-specific environment left behind by a previous session.
$PathSeparator = [System.IO.Path]::PathSeparator
if ([string]::IsNullOrWhiteSpace($env:PYTHONPATH)) {
    $env:PYTHONPATH = $SrcRoot
} else {
    $env:PYTHONPATH = "$SrcRoot$PathSeparator$($env:PYTHONPATH)"
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

$MarketInventory = [ordered]@{}
foreach ($Symbol in @("ETHUSDC", "BTCUSDC", "ETHBTC")) {
    $MarketInventory[$Symbol] = Assert-SymbolInventory -Symbol $Symbol -Root $RawRootFull -EndDay $DataEndDay
}

if (-not $ReportsRoot) {
    $ReportsRoot = Join-Path $RepoRoot "reports\research_loop"
}
$ReportsRootFull = [System.IO.Path]::GetFullPath($ReportsRoot)
New-Item -Path $ReportsRootFull -ItemType Directory -Force | Out-Null

$RunLockPath = Join-Path $ReportsRootFull "production_research.active.lock"
try {
    $RunLock = [System.IO.File]::Open(
        $RunLockPath,
        [System.IO.FileMode]::OpenOrCreate,
        [System.IO.FileAccess]::ReadWrite,
        [System.IO.FileShare]::None
    )
} catch [System.IO.IOException] {
    throw "Another production research process already owns the run lock: $RunLockPath"
}

try {
$StartedAtUtc = [DateTime]::UtcNow
$Timestamp = $StartedAtUtc.ToString("yyyyMMddTHHmmssZ")
$ConsoleLog = Join-Path $ReportsRootFull "production_research_$Timestamp.console.log"

Invoke-Checked -FilePath "py" -ArgumentList @("-3.12", "-m", "pytest", "-q") -Description "Full Python test suite"
Invoke-Checked -FilePath "py" -ArgumentList @("-3.12", "-m", "compileall", "-q", "src") -Description "Python source compilation"
Invoke-Checked -FilePath "py" -ArgumentList @(
    "-3.12",
    "-c",
    "import ethusdc_bot.backtest.research_loop_runner; import ethusdc_bot.backtest.research_supervisor; print('RESEARCH_MODULE_IMPORT_OK')"
) -Description "Research module import check"

$ResearchArguments = @(
    "-3.12",
    "-m",
    "ethusdc_bot.backtest.research_supervisor",
    "--raw-root", $RawRootFull,
    "--reports-root", $ReportsRootFull,
    "--max-cycles", "$MaxCycles",
    "--max-candidates-per-cycle", "40",
    "--tested-candidates-per-cycle", "12",
    "--walk-forward-candidates-per-cycle", "3",
    "--finalists-per-cycle", "2",
    "--walk-forward-folds", "6",
    "--rolling-origin-limit", "3",
    "--data-end-day", $DataEndDay,
    "--enable-context"
)

Write-Host "==> Production Research Protocol v2 with aligned public context"
Write-Host "Branch: $GitBranch"
Write-Host "Commit: $GitCommit"
Write-Host "Source root: $SrcRoot"
Write-Host "Raw root: $RawRootFull"
Write-Host "Data end day: $DataEndDay"
Write-Host "Reports root: $ReportsRootFull"
Write-Host "Max cycles: $MaxCycles"
foreach ($Symbol in $MarketInventory.Keys) {
    $Item = $MarketInventory[$Symbol]
    Write-Host "$Symbol inventory: ZIP=$($Item.zip_count) CHECKSUM=$($Item.checksum_count) first=$($Item.first_file) last=$($Item.last_file)"
}

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

$ReportTxtLine = $ResearchOutput | Where-Object { "$_" -match '^Report TXT:\s+(.+)$' } | Select-Object -Last 1
if (-not $ReportTxtLine -or "$ReportTxtLine" -notmatch '^Report TXT:\s+(.+)$') {
    throw "Research completed without reporting a TXT path. Console log: $ConsoleLog"
}
$ReportTxt = $Matches[1].Trim()
if (-not [System.IO.Path]::IsPathRooted($ReportTxt)) {
    $ReportTxt = Join-Path $RepoRoot $ReportTxt
}
$ReportTxt = [System.IO.Path]::GetFullPath($ReportTxt)
if (-not (Test-Path $ReportTxt -PathType Leaf)) {
    throw "Reported TXT does not exist: $ReportTxt"
}

# The canonical TXT is intentionally compact. Never deserialize the multi-GB
# detail JSON in Windows PowerShell after the runner has already validated and
# written it.
$ReportText = @(Get-Content -Path $ReportTxt -Encoding UTF8)
$LoopRunLine = $ReportText | Where-Object { "$_" -match '^Loop-Run-ID:\s+(.+)$' } | Select-Object -Last 1
if (-not $LoopRunLine -or "$LoopRunLine" -notmatch '^Loop-Run-ID:\s+(.+)$') {
    throw "Compact report is missing Loop-Run-ID"
}
$LoopRunId = $Matches[1].Trim()
$CyclesLine = $ReportText | Where-Object { "$_" -match '^Cycles executed:\s+(\d+)/(\d+)$' } | Select-Object -Last 1
if (-not $CyclesLine -or "$CyclesLine" -notmatch '^Cycles executed:\s+(\d+)/(\d+)$') {
    throw "Compact report is missing cycle totals"
}
$CyclesExecuted = [int]$Matches[1]
$ReportedMaxCycles = [int]$Matches[2]
if ($ReportedMaxCycles -ne $MaxCycles) {
    throw "Compact report max cycles differ from requested max cycles"
}
$StopLine = $ReportText | Where-Object { "$_" -match '^Stop reason:\s+(.+)$' } | Select-Object -Last 1
if (-not $StopLine -or "$StopLine" -notmatch '^Stop reason:\s+(.+)$') {
    throw "Compact report is missing stop reason"
}
$StopReason = $Matches[1].Trim()
$FreezeLine = $ReportText | Where-Object { "$_" -match '^Freeze status:\s+(.+)$' } | Select-Object -Last 1
if (-not $FreezeLine -or "$FreezeLine" -notmatch '^Freeze status:\s+(.+)$') {
    throw "Compact report is missing freeze status"
}
$FreezeStatus = $Matches[1].Trim()
$BestValidationLine = $ReportText | Where-Object { "$_" -match '^Best validation:\s+(.+)$' } | Select-Object -Last 1
$BestValidation = if ($BestValidationLine -and "$BestValidationLine" -match '^Best validation:\s+(.+)$') { $Matches[1].Trim() } else { "not_reported" }

$StageLines = @($ResearchOutput | Where-Object {
    "$_" -match '^cycle \d+/\d+: generated=40 tested=12 walk_forward=3 finalists=2 selected_rank='
})
$ProofLines = @($ResearchOutput | Where-Object {
    "$_" -match '^cycle \d+/\d+ proof: context_research\.enabled=true context_generated=6 context_tested=2 walk_forward_folds=6 rolling_origin_limit=3 audit_evaluated=false final_holdout_evaluated=false$'
})
if ($StageLines.Count -ne $CyclesExecuted -or $ProofLines.Count -ne $CyclesExecuted) {
    throw "Every completed cycle must prove exact 40/12/3/2 stages and enabled PR12 context"
}
if (-not ($ReportText -contains "Holdout evaluated: False") -or
    -not ($ReportText -contains "Consumed audit affects selection: False") -or
    -not ($ReportText -contains "Live/Paper/Testtrade locked. No orders, no Trading API, no API keys.")) {
    throw "Compact report is missing canonical audit, holdout, or safety locks"
}

$Manifest = [ordered]@{
    schema_version = 1
    run_kind = "production_selection_research_with_context"
    started_at_utc = $StartedAtUtc.ToString("o")
    completed_at_utc = [DateTime]::UtcNow.ToString("o")
    git_branch = $GitBranch
    git_commit = $GitCommit
    working_tree_clean = $true
    source_root = $SrcRoot
    pythonpath = $env:PYTHONPATH
    raw_root = $RawRootFull
    data_end_day = $DataEndDay
    reports_root = $ReportsRootFull
    run_lock_path = $RunLockPath
    market_inventory = $MarketInventory
    context_enabled = $true
    context_trade_symbol = "ETHUSDC"
    context_only_symbols = @("BTCUSDC", "ETHBTC")
    max_cycles = $MaxCycles
    canonical_stage_budgets = [ordered]@{
        generated = 40
        tested = 12
        walk_forward = 3
        finalists = 2
    }
    report_json = $ReportJson
    report_txt = $ReportTxt
    console_log = $ConsoleLog
    loop_run_id = $LoopRunId
    cycles_executed = $CyclesExecuted
    stop_reason = $StopReason
    freeze_status = $FreezeStatus
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
Write-Host "Run ID: $LoopRunId"
Write-Host "Cycles: $CyclesExecuted"
Write-Host "Stop reason: $StopReason"
Write-Host "Freeze status: $FreezeStatus"
Write-Host "Best validation: $BestValidation"
Write-Host "Last frontier: $($StageLines | Select-Object -Last 1)"
Write-Host "Context proof: $($ProofLines | Select-Object -Last 1)"
Write-Host "Final holdout evaluated: False"
Write-Host "Live/Paper/Testtrade/Orders: locked"
Write-Host "Report JSON: $ReportJson"
Write-Host "Report TXT: $ReportTxt"
Write-Host "Manifest: $ManifestPath"
Write-Host "Console log: $ConsoleLog"
} finally {
    $RunLock.Dispose()
}
