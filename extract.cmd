@echo off
setlocal
set "ROOT=%~dp0"
python "%ROOT%tools\gate\gate.py" --verify-rom
if errorlevel 1 exit /b 1
echo extract done
