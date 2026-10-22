@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 goto failed
)
if exist "artifacts\wheels" (
    ".venv\Scripts\python.exe" -m pip install --no-index --find-links artifacts\wheels -r requirements.txt
    if not errorlevel 1 goto done
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
:done
echo Setup complete. Open start.cmd.
pause
exit /b 0
:failed
echo Setup failed. Check Python installation and network access.
pause
exit /b 1

