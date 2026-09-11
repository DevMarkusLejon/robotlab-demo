@echo off
cd /d "%~dp0"
where pythonw >nul 2>nul
if errorlevel 1 (
  echo Python saknas. Installera Python 3.11 eller senare och aktivera PATH.
  pause
  exit /b 1
)
start "" pythonw -m robotlab.launcher
