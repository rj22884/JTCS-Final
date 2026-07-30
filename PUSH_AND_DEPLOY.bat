@echo off
title JTCS ERP - ONE CLICK Push + Deploy
color 0A
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================
REM  E:\Git\JTCS Final\PUSH_AND_DEPLOY.bat
REM
REM  1) Commit message poochhega
REM  2) VPS password poochhega   (root@200.141.5.68)
REM  3) GitHub push + VPS deploy (local VPS changes auto-fix)
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
echo   Local folder : %CD%
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

set "VPS_HOST=200.141.5.68"
set "VPS_USER=root"
set "VPS_PORT=22"
set "VPS_PATH=~/JTCS-final"
set "VPS_SSH_KEY="
set "VPS_PASSWORD="
set "COMMIT_MSG="

if exist "deploy_vps.env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in ("deploy_vps.env") do (
        if not "%%A"=="" set "%%A=%%B"
    )
)

if "!VPS_HOST!"=="" set "VPS_HOST=200.141.5.68"
if "!VPS_USER!"=="" set "VPS_USER=root"
if "!VPS_PORT!"=="" set "VPS_PORT=22"
if "!VPS_PATH!"=="" set "VPS_PATH=~/JTCS-final"

echo   VPS target : !VPS_USER!@!VPS_HOST!
echo   VPS path   : !VPS_PATH!
echo.

echo [INPUT] Commit message likho
echo -------------------------
set /p COMMIT_MSG=Commit message: 
if "!COMMIT_MSG!"=="" (
    for /f "tokens=1-3 delims=/ " %%a in ("%date%") do set "D=%%a-%%b-%%c"
    for /f "tokens=1-2 delims=:." %%a in ("%time%") do set "T=%%a%%b"
    set "COMMIT_MSG=update !D! !T!"
    echo [OK] Auto message: !COMMIT_MSG!
)
echo.

echo [INPUT] VPS password likho  ^(!VPS_USER!@!VPS_HOST!^)
echo -------------------------
set /p VPS_PASSWORD=VPS password: 
if "!VPS_PASSWORD!"=="" (
    echo [ERROR] Password khali nahi chhod sakte.
    pause
    exit /b 1
)
echo.

echo [1/2] GitHub PUSH...
echo -------------------------
git status -sb
echo.

git add -A
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "!COMMIT_MSG!"
    if errorlevel 1 (
        echo [ERROR] Commit fail.
        pause
        exit /b 1
    )
    echo [OK] Commit: !COMMIT_MSG!
) else (
    echo [OK] Commit ki zarurat nahi.
)

echo.
git push -u origin HEAD
if errorlevel 1 (
    echo [ERROR] GitHub push fail.
    pause
    exit /b 1
)
echo [OK] GitHub push complete.
echo.

for /f "delims=" %%B in ('git rev-parse --abbrev-ref HEAD') do set "LOCAL_BRANCH=%%B"
if "!LOCAL_BRANCH!"=="" set "LOCAL_BRANCH=main"
echo   Deploy branch on VPS: !LOCAL_BRANCH!
echo.

echo [2/2] VPS DEPLOY...
echo -------------------------
echo Connecting !VPS_USER!@!VPS_HOST! ...
echo.

REM Self-contained remote script — no dependency on script already existing on VPS
set "REMOTE_CMD=set -e; cd !VPS_PATH!; echo '== VPS deploy start =='; if [ -f erp/.env ]; then cp erp/.env /tmp/jtcs.env.bak; echo 'backed up erp/.env'; fi; git fetch origin; git checkout !LOCAL_BRANCH! 2>/dev/null || git checkout -B !LOCAL_BRANCH! origin/!LOCAL_BRANCH! 2>/dev/null || git checkout main; git reset --hard origin/!LOCAL_BRANCH! 2>/dev/null || git reset --hard origin/main; if [ -f /tmp/jtcs.env.bak ]; then cp /tmp/jtcs.env.bak erp/.env; echo 'restored erp/.env'; fi; if [ -f scripts/vps_pull_update.sh ]; then bash scripts/vps_pull_update.sh; else echo 'basic pull/reset done'; cd erp; python3 -m pip install -r requirements.txt -q 2>/dev/null || true; fi; ls erp/scripts/check_vps_mail.py 2>/dev/null || true; echo '== VPS deploy OK =='"

where plink >nul 2>&1
if not errorlevel 1 (
    echo Using plink...
    echo y | plink -batch -ssh -P !VPS_PORT! -pw "!VPS_PASSWORD!" !VPS_USER!@!VPS_HOST! "!REMOTE_CMD!"
    if errorlevel 1 goto deploy_fail
    goto deploy_ok
)

set "PW_FILE=%TEMP%\jtcs_vps_pw_%RANDOM%.txt"
set "ASKPASS_FILE=%TEMP%\jtcs_ssh_askpass_%RANDOM%.cmd"
powershell -NoProfile -Command ^
  "$ErrorActionPreference='Stop';" ^
  "Set-Content -Path $env:PW_FILE -Value $env:VPS_PASSWORD -Encoding ASCII -NoNewline;" ^
  "$ask = @('@echo off','type \"' + $env:PW_FILE + '\"');" ^
  "Set-Content -Path $env:ASKPASS_FILE -Value $ask -Encoding ASCII"

if not exist "!ASKPASS_FILE!" (
    echo [ERROR] Password helper file nahi bani.
    pause
    exit /b 1
)

set "SSH_ASKPASS=!ASKPASS_FILE!"
set "SSH_ASKPASS_REQUIRE=force"
set "DISPLAY=jtcs:0"

ssh -p !VPS_PORT! -o StrictHostKeyChecking=accept-new -o PreferredAuthentications=password -o PubkeyAuthentication=no !VPS_USER!@!VPS_HOST! "!REMOTE_CMD!"
set "SSH_EXIT=!errorlevel!"

del /q "!ASKPASS_FILE!" >nul 2>&1
del /q "!PW_FILE!" >nul 2>&1
set "SSH_ASKPASS="
set "SSH_ASKPASS_REQUIRE="
set "DISPLAY="
set "VPS_PASSWORD="

if not "!SSH_EXIT!"=="0" goto deploy_fail
goto deploy_ok

:deploy_fail
del /q "!ASKPASS_FILE!" >nul 2>&1
del /q "!PW_FILE!" >nul 2>&1
echo.
echo [ERROR] VPS deploy fail.
echo.
echo VPS pe yeh 4 lines chalao ^(ek baar^):
echo   cd ~/JTCS-final
echo   cp erp/.env /tmp/jtcs.env.bak
echo   git fetch origin ^&^& git reset --hard origin/main
echo   cp /tmp/jtcs.env.bak erp/.env
echo.
pause
exit /b 1

:deploy_ok
set "VPS_PASSWORD="
echo.
echo ========================================================
echo   HO GAYA - Push + Deploy DONE
echo ========================================================
echo   Commit : !COMMIT_MSG!
echo   VPS    : http://!VPS_HOST!:8000/login
echo.
echo   Mail test on VPS:
echo     cd ~/JTCS-final/erp
echo     python3 scripts/check_vps_mail.py
echo ========================================================
echo.
pause
endlocal
