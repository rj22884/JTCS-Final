@echo off
REM Install a Startup shortcut so the bridge runs when this Windows PC is on.
set "ROOT=%~dp0.."
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SRC=%ROOT%\scripts\run_other_login_bridge.bat"
set "DST=%STARTUP%\JTCS Other Login Bridge.cmd"

if not exist "%SRC%" (
    echo [FAIL] Missing %SRC%
    exit /b 1
)
if not exist "%STARTUP%" mkdir "%STARTUP%" >nul 2>&1

> "%DST%" (
    echo @echo off
    echo call "%SRC%"
)

echo Startup: %DST%
exit /b 0
