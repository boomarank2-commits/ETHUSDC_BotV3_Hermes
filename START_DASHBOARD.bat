@echo off
setlocal
cd /d "%~dp0"
echo Starting ETHUSDC Bot V3 Hermes Dashboard only.
echo This opens the local status UI only; trading actions remain unavailable.
set PYTHONPATH=src
python -m ethusdc_bot.ui.dashboard
if errorlevel 1 (
  echo.
  echo Dashboard exited with an error. This window stays open so the message can be read.
  pause
)
endlocal
