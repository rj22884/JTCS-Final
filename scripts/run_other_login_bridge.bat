@echo off
setlocal
REM Never block JTCS_ERP option 1. No wmic (removed on new Windows).
for %%I in ("%~dp0..") do set "ROOT=%%~fI"
set "PY=%ROOT%\erp\.venv\Scripts\python.exe"
set "AGENT=%ROOT%\erp\scripts\other_login_local_bridge.py"
if not exist "%AGENT%" exit /b 0
if not exist "%PY%" (
    where python >nul 2>&1 || exit /b 0
    set "PY=python"
)
start "JTCS Other Login Bridge" /MIN /D "%ROOT%\erp" "%PY%" "%AGENT%"
exit /b 0
