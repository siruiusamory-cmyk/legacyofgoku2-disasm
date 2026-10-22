@echo off
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"
python tools\check_links.py
if errorlevel 1 exit /b 1
python tools\lint\lints.py
if errorlevel 1 exit /b 1
python -m pytest -q tools\test_check_links.py
