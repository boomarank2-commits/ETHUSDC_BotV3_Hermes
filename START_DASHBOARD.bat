@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PYTHONPATH=%~dp0src"
set "HERMES_DATA_ROOT=C:\TradingBot\data\ETHUSDC_BotV3_Hermes"

where py >nul 2>&1
if errorlevel 1 (
  echo.
  echo FEHLER: Python Launcher ^(py^) wurde nicht gefunden.
  echo Erwartet wird Python 3.12.
  pause
  exit /b 1
)

set "HERMES_GIT_BRANCH="
set "HERMES_GIT_COMMIT="
for /f "delims=" %%B in ('git branch --show-current 2^>nul') do set "HERMES_GIT_BRANCH=%%B"
for /f "delims=" %%C in ('git rev-parse --short HEAD 2^>nul') do set "HERMES_GIT_COMMIT=%%C"

if not defined HERMES_GIT_BRANCH (
  echo.
  echo FEHLER: Das Dashboard befindet sich nicht auf einem benannten Git-Branch.
  echo Ein reproduzierbarer Backtest darf nicht von detached HEAD gestartet werden.
  echo Bitte zuerst den vorgesehenen Dashboard-Branch auschecken.
  pause
  exit /b 1
)

echo Starting ETHUSDC Bot V3 Hermes Dashboard.
echo Code root: %~dp0
echo Data/report root: %HERMES_DATA_ROOT%
echo Branch: %HERMES_GIT_BRANCH%
echo Commit: %HERMES_GIT_COMMIT%
echo This is the single user entry point. Trading actions remain unavailable.
echo.

py -3.12 -m ethusdc_bot.ui.dashboard
if errorlevel 1 (
  echo.
  echo Dashboard exited with an error. This window stays open so the message can be read.
  pause
  exit /b 1
)

endlocal
