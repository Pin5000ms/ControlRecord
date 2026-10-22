@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 goto failed
".venv\Scripts\python.exe" tools\make_icon.py
if errorlevel 1 goto failed
".venv\Scripts\python.exe" tools\build_portable.py
if errorlevel 1 goto failed
echo Build complete. See dist folder.
pause
exit /b 0
:failed
echo Build failed. See error above.
pause
exit /b 1

