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

for /f "usebackq eol=# tokens=1,* delims==" %%A in ("deploy_vps.env") do (
    if not "%%A"=="" set "%%A=%%B"
)

if "%VPS_HOST%"=="" (
    echo ERROR: VPS_HOST missing in deploy_vps.env
    pause
    exit /b 1
)
if "%VPS_USER%"=="" set "VPS_USER=root"
if "%VPS_PORT%"=="" set "VPS_PORT=22"
if "%VPS_PATH%"=="" set "VPS_PATH=~/JTCS-final"

where ssh >nul 2>&1
if errorlevel 1 (
    echo ERROR: ssh not found.
    echo Install OpenSSH Client: Settings - Apps - Optional features - OpenSSH Client
    pause
    exit /b 1
)

echo.
echo ========================================
echo   JTCS ERP - Deploy to VPS
echo ========================================
echo   Host : %VPS_USER%@%VPS_HOST%:%VPS_PORT%
echo   Path : %VPS_PATH%
echo.
echo Step 1/2: Push local code to GitHub first? (Y/N)
set /p DOPUSH="> "
if /i "%DOPUSH%"=="Y" (
    call "%~dp0push_to_git.bat"
)

echo.
echo Step 2/2: Pull + update on VPS via SSH...
echo.

if "%VPS_SSH_KEY%"=="" (
    ssh -p %VPS_PORT% -o StrictHostKeyChecking=accept-new %VPS_USER%@%VPS_HOST% "cd %VPS_PATH% && bash scripts/vps_pull_update.sh"
) else (
    ssh -p %VPS_PORT% -i "%VPS_SSH_KEY%" -o StrictHostKeyChecking=accept-new %VPS_USER%@%VPS_HOST% "cd %VPS_PATH% && bash scripts/vps_pull_update.sh"
)

if errorlevel 1 (
    echo.
    echo Deploy command failed.
    echo Tips:
    echo   - Make sure SSH login works: ssh %VPS_USER%@%VPS_HOST%
    echo   - On VPS, repo must exist at %VPS_PATH%
    echo   - Manual VPS update:
    echo       cd %VPS_PATH%
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
