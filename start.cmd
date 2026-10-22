@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Please run setup.cmd first, or use dist\ControlRecord\ControlRecord.exe.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "main.py"

