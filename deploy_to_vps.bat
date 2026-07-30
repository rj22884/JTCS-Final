@echo off
title JTCS ERP - Deploy to VPS
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"
if errorlevel 1 (
    echo ERROR: Could not open project folder.
    pause
    exit /b 1
)

if not exist "deploy_vps.env" (
    echo.
    echo deploy_vps.env not found.
    echo Creating from deploy_vps.env.example ...
    if not exist "deploy_vps.env.example" (
        echo ERROR: deploy_vps.env.example missing.
        pause
        exit /b 1
    )
    copy /Y "deploy_vps.env.example" "deploy_vps.env" >nul
    echo.
    echo Created deploy_vps.env — edit host/user/path, then run again.
    notepad "deploy_vps.env"
    pause
    exit /b 0
)

REM Load env; strip CR so values are not path^M
for /f "usebackq eol=# tokens=1,* delims==" %%A in (`powershell -NoProfile -Command "Get-Content -LiteralPath 'deploy_vps.env' | ForEach-Object { $_ -replace '`r','' }"`) do (
    if not "%%A"=="" set "%%A=%%B"
)

if "%VPS_HOST%"=="" (
    echo ERROR: VPS_HOST missing in deploy_vps.env
    pause
    exit /b 1
)
if "%VPS_USER%"=="" set "VPS_USER=root"
if "%VPS_PORT%"=="" set "VPS_PORT=22"
if "%VPS_PATH%"=="" set "VPS_PATH=/root/JTCS-final"
if /i "%VPS_PATH%"=="~/JTCS-final" set "VPS_PATH=/root/JTCS-final"
if /i "%VPS_PATH%"=="~/JTCS-Final" set "VPS_PATH=/root/JTCS-final"

where ssh >nul 2>&1
if errorlevel 1 (
    echo ERROR: ssh not found.
    echo Install OpenSSH Client: Settings - Apps - Optional features - OpenSSH Client
    pause
    exit /b 1
)

for /f "delims=" %%B in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "LOCAL_BRANCH=%%B"
if "!LOCAL_BRANCH!"=="" set "LOCAL_BRANCH=main"

echo.
echo ========================================
echo   JTCS ERP - Deploy to VPS
echo ========================================
echo   Host   : %VPS_USER%@%VPS_HOST%:%VPS_PORT%
echo   Path   : %VPS_PATH%
echo   Branch : !LOCAL_BRANCH!
echo   SQL    : DATA SAFE (schema-only; no overwrite)
echo.
echo Step 1/2: Push local code to GitHub first? (Y/N)
set /p DOPUSH="> "
if /i "%DOPUSH%"=="Y" (
    call "%~dp0push_to_git.bat"
)

echo.
echo Step 2/2: Pull + update on VPS via SSH...
echo   Tip: "Permission denied" = galat password. Sahi password do.
echo.

set "REMOTE_SH=%TEMP%\jtcs_vps_deploy_%RANDOM%.sh"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build_vps_deploy_remote.ps1" -OutFile "!REMOTE_SH!" -RepoPath "%VPS_PATH%" -Branch "!LOCAL_BRANCH!"
if errorlevel 1 (
    echo ERROR: Temp deploy script nahi bani.
    pause
    exit /b 1
)
if not exist "!REMOTE_SH!" (
    echo ERROR: Temp deploy script nahi bani.
    pause
    exit /b 1
)

if not "%VPS_SSH_KEY%"=="" (
    ssh -p %VPS_PORT% -i "%VPS_SSH_KEY%" -o StrictHostKeyChecking=accept-new %VPS_USER%@%VPS_HOST% "bash -s" < "!REMOTE_SH!"
) else (
    ssh -p %VPS_PORT% -o StrictHostKeyChecking=accept-new %VPS_USER%@%VPS_HOST% "bash -s" < "!REMOTE_SH!"
)
set "SSH_EXIT=!errorlevel!"
del /q "!REMOTE_SH!" >nul 2>&1

if not "!SSH_EXIT!"=="0" (
    echo.
    echo Deploy command failed.
    echo Tips:
    echo   - Permission denied = wrong SSH password
    echo   - Test login: ssh %VPS_USER%@%VPS_HOST%
    echo   - Confirm folder on VPS: %VPS_PATH%
    echo   - Manual:
    echo       cd /root/JTCS-final
    echo       git fetch origin ^&^& git reset --hard origin/!LOCAL_BRANCH!
    echo       bash scripts/vps_pull_update.sh
    pause
    exit /b 1
)

echo.
echo ========================================
echo   DONE - VPS updated from GitHub
echo ========================================
echo   Open: http://%VPS_HOST%:8000/login
echo ========================================
echo.
pause
endlocal
