@echo off
title JTCS ERP - ONE CLICK Push + Deploy
color 0A
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================
REM  E:\Git\JTCS Final\PUSH_AND_DEPLOY.bat
REM
REM  1) Commit message poochhega
REM  2) VPS password poochhega
REM  3) GitHub push + VPS deploy
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
echo   SQL DATA     : SAFE (never overwritten on deploy)
echo   DB changes   : schema only (new tables/columns)
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

where powershell >nul 2>&1
if errorlevel 1 (
    echo [ERROR] PowerShell nahi mila.
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
echo Tip: Permission denied = galat password.
echo.

REM Prefer absolute path over ~/JTCS-final
if /i "!VPS_PATH!"=="~/JTCS-final" set "VPS_PATH=/root/JTCS-final"
if /i "!VPS_PATH!"=="~/JTCS-Final" set "VPS_PATH=/root/JTCS-final"
if "!VPS_PATH!"=="" set "VPS_PATH=/root/JTCS-final"

REM Unix-LF remote script (Windows CRLF breaks bash on VPS)
set "REMOTE_SH=%TEMP%\jtcs_vps_deploy_%RANDOM%.sh"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build_vps_deploy_remote.ps1" -OutFile "!REMOTE_SH!" -RepoPath "!VPS_PATH!" -Branch "!LOCAL_BRANCH!"
if errorlevel 1 (
    echo [ERROR] Temp deploy script nahi bani.
    pause
    exit /b 1
)
if not exist "!REMOTE_SH!" (
    echo [ERROR] Temp deploy script nahi bani.
    pause
    exit /b 1
)

set "SSH_EXIT=1"

where plink >nul 2>&1
if not errorlevel 1 (
    echo Using plink...
    plink -batch -ssh -P !VPS_PORT! -pw "!VPS_PASSWORD!" !VPS_USER!@!VPS_HOST! "bash -s" < "!REMOTE_SH!"
    set "SSH_EXIT=!errorlevel!"
    goto after_ssh
)

REM OpenSSH + password via SSH_ASKPASS; remote script via stdin (avoids CMD || && bugs)
set "PW_FILE=%TEMP%\jtcs_vps_pw_%RANDOM%.txt"
set "ASKPASS_FILE=%TEMP%\jtcs_ssh_askpass_%RANDOM%.cmd"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "Set-Content -LiteralPath $env:PW_FILE -Value $env:VPS_PASSWORD -Encoding ascii -NoNewline;" ^
  "$lines = @('@echo off', ('type \"{0}\"' -f $env:PW_FILE));" ^
  "Set-Content -LiteralPath $env:ASKPASS_FILE -Value $lines -Encoding ascii;" ^
  "$env:SSH_ASKPASS = $env:ASKPASS_FILE;" ^
  "$env:SSH_ASKPASS_REQUIRE = 'force';" ^
  "$env:DISPLAY = 'jtcs:0';" ^
  "$target = $env:VPS_USER + '@' + $env:VPS_HOST;" ^
  "Get-Content -LiteralPath $env:REMOTE_SH -Raw | & ssh -p $env:VPS_PORT -o StrictHostKeyChecking=accept-new -o PreferredAuthentications=password -o PubkeyAuthentication=no $target bash -s;" ^
  "exit $LASTEXITCODE"

set "SSH_EXIT=!errorlevel!"

:after_ssh
del /q "!REMOTE_SH!" >nul 2>&1
del /q "!ASKPASS_FILE!" >nul 2>&1
del /q "!PW_FILE!" >nul 2>&1
set "SSH_ASKPASS="
set "SSH_ASKPASS_REQUIRE="
set "DISPLAY="
set "VPS_PASSWORD="
set "PW_FILE="
set "ASKPASS_FILE="
set "REMOTE_SH="

if not "!SSH_EXIT!"=="0" goto deploy_fail
goto deploy_ok

:deploy_fail
del /q "!REMOTE_SH!" >nul 2>&1
del /q "!ASKPASS_FILE!" >nul 2>&1
del /q "!PW_FILE!" >nul 2>&1
echo.
echo [ERROR] VPS deploy fail.
echo.
echo Manual check:
echo   ssh !VPS_USER!@!VPS_HOST!
echo   cd !VPS_PATH!
echo   export BRANCH=!LOCAL_BRANCH!
echo   bash scripts/vps_pull_update.sh
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
echo   Branch : !LOCAL_BRANCH!
echo   VPS    : http://!VPS_HOST!:8000/login
echo   SQL    : live data preserved (schema-only update)
echo.
echo   Mail test on VPS:
echo     cd ~/JTCS-final/erp
echo     python3 scripts/check_vps_mail.py
echo ========================================================
echo.
pause
endlocal
