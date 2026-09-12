@echo off
cd /d "%~dp0"
where pythonw >nul 2>nul
if errorlevel 1 (
  echo Python 3.11 eller senare med Tkinter kravs.
  pause
  exit /b 1
)
start "" pythonw -m robotlab.smc_ui
