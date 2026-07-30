@echo off
title JTCS ERP - ONE CLICK Push + Deploy
color 0A
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================
REM  File name : PUSH_AND_DEPLOY.bat
REM  Location  : E:\Git\JTCS Final\PUSH_AND_DEPLOY.bat
REM
REM  Double-click = GitHub PUSH + VPS DEPLOY
REM ============================================================

cd /d "%~dp0"
if errorlevel 1 (
    echo [ERROR] Folder open nahi hua: %~dp0
    pause
    exit /b 1
)

echo.
echo ========================================================
echo   JTCS ERP - ONE CLICK: Push + Deploy
echo ========================================================
echo   Local : %CD%
echo.

where git >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Git nahi mila. Git for Windows install karo.
    pause
    exit /b 1
)

where ssh >nul 2>&1
if errorlevel 1 (
    echo [ERROR] SSH nahi mila.
    echo Windows Settings - Optional features - OpenSSH Client install karo.
    pause
    exit /b 1
)

REM ---- VPS settings (edit yahan agar IP badle) ----
set "VPS_HOST=200.141.5.68"
set "VPS_USER=root"
set "VPS_PORT=22"
set "VPS_PATH=~/JTCS-final"
set "VPS_SSH_KEY="

if exist "deploy_vps.env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in ("deploy_vps.env") do (
        if not "%%A"=="" set "%%A=%%B"
    )
)

if "%VPS_HOST%"=="" set "VPS_HOST=200.141.5.68"
if "%VPS_USER%"=="" set "VPS_USER=root"
if "%VPS_PORT%"=="" set "VPS_PORT=22"
if "%VPS_PATH%"=="" set "VPS_PATH=~/JTCS-final"

echo   VPS   : %VPS_USER%@%VPS_HOST%
echo   Path  : %VPS_PATH%
echo.

REM =========================
echo [1/2] GitHub PUSH...
echo -------------------------
git status -sb
echo.

for /f "tokens=1-3 delims=/ " %%a in ("%date%") do set "D=%%a-%%b-%%c"
for /f "tokens=1-2 delims=:." %%a in ("%time%") do set "T=%%a%%b"
set "MSG=one-click deploy %D% %T%"

git add -A

git diff --cached --quiet
if errorlevel 1 (
    git commit -m "!MSG!"
    if errorlevel 1 (
        echo [ERROR] Commit fail.
        pause
        exit /b 1
    )
    echo [OK] Commit ho gaya.
) else (
    echo [OK] Commit ki zarurat nahi.
)

echo.
git push -u origin HEAD
if errorlevel 1 (
    echo [ERROR] GitHub push fail. Login/internet check karo.
    pause
    exit /b 1
)
echo [OK] GitHub push complete.
echo.

for /f "delims=" %%B in ('git rev-parse --abbrev-ref HEAD') do set "LOCAL_BRANCH=%%B"
if "%LOCAL_BRANCH%"=="" set "LOCAL_BRANCH=main"
echo   Deploy branch: %LOCAL_BRANCH%
echo.

REM =========================
echo [2/2] VPS DEPLOY...
echo -------------------------
echo Connecting %VPS_USER%@%VPS_HOST% ...
echo.

REM Keep remote command free of CMD metacharacters (|| && 2>) — those break Windows ssh lines.
set "REMOTE_CMD=cd %VPS_PATH%; export BRANCH=%LOCAL_BRANCH%; bash scripts/vps_pull_update.sh"

if "%VPS_SSH_KEY%"=="" (
    ssh -p %VPS_PORT% -o StrictHostKeyChecking=accept-new %VPS_USER%@%VPS_HOST% "%REMOTE_CMD%"
) else (
    ssh -p %VPS_PORT% -i "%VPS_SSH_KEY%" -o StrictHostKeyChecking=accept-new %VPS_USER%@%VPS_HOST% "%REMOTE_CMD%"
)

if errorlevel 1 (
    echo.
    echo [ERROR] VPS deploy fail.
    echo Pehli baar yeh chalao aur password do:
    echo   ssh %VPS_USER%@%VPS_HOST%
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================================
echo   HO GAYA - Push + Deploy DONE
echo ========================================================
echo   Site: http://%VPS_HOST%:8000/login
echo ========================================================
echo.
pause
endlocal
