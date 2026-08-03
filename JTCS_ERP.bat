@echo off
title JTCS ERP
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

REM --- ANSI colors (Windows 10+) ---
for /F %%A in ('echo prompt $E^| cmd') do set "ESC=%%A"
set "C_RESET=%ESC%[0m"
set "C_GREEN=%ESC%[92m"
set "C_RED=%ESC%[91m"
set "C_YELLOW=%ESC%[93m"
set "C_CYAN=%ESC%[96m"
set "C_BOLD=%ESC%[1m"

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "LOG_DIR=%ROOT%\deployment\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1

call :load_vps_env
call :init_branch

:menu
cls
echo.
echo  %C_CYAN%========================================%C_RESET%
echo  %C_BOLD%JTCS ERP%C_RESET%
echo  %C_CYAN%========================================%C_RESET%
echo  Branch : %C_YELLOW%%LOCAL_BRANCH%%C_RESET%
echo  Live   : %PUBLIC_HEALTH_URL%
echo  Local  : http://localhost:8000
echo  %C_CYAN%========================================%C_RESET%
echo.
echo   1. Run at local
echo   2. Push and deploy
echo   0. Exit
echo.
set "choice="
set /p choice="Select option (0-2): "
if defined choice set "choice=!choice: =!"

if /i "!choice!"=="1" goto run_local
if /i "!choice!"=="2" goto push_and_deploy
if /i "!choice!"=="0" exit /b 0
echo.
echo %C_RED%[FAIL]%C_RESET% Invalid option: "!choice!"
pause
goto menu

REM =============================================================================
REM HELPERS
REM =============================================================================
:load_vps_env
set "VPS_HOST=200.141.5.68"
set "VPS_USER=root"
set "VPS_PORT=22"
set "VPS_PATH=/root/JTCS-final"
set "PUBLIC_HEALTH_URL=https://app.jtcsxpert.com/health"
if exist "%ROOT%\deploy_vps.env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in (`powershell -NoProfile -Command "Get-Content -LiteralPath '%ROOT%\deploy_vps.env' | ForEach-Object { $_ -replace '`r','' }"`) do (
        if not "%%A"=="" set "%%A=%%B"
    )
)
if /i "!VPS_PATH!"=="~/JTCS-final" set "VPS_PATH=/root/JTCS-final"
if "!PUBLIC_HEALTH_URL!"=="" set "PUBLIC_HEALTH_URL=https://app.jtcsxpert.com/health"
exit /b 0

:init_branch
set "LOCAL_BRANCH="
for /f "delims=" %%B in ('git -C "%ROOT%" branch --show-current 2^>nul') do set "LOCAL_BRANCH=%%B"
if "!LOCAL_BRANCH!"=="" (
    for /f "delims=" %%B in ('git -C "%ROOT%" rev-parse --abbrev-ref HEAD 2^>nul') do set "LOCAL_BRANCH=%%B"
)
if "!LOCAL_BRANCH!"=="" set "LOCAL_BRANCH=DETACHED"
exit /b 0

:require_git
where git >nul 2>&1
if errorlevel 1 (
    echo %C_RED%[FAIL]%C_RESET% git not found in PATH.
    pause
    goto menu
)
exit /b 0

:require_ssh
where ssh >nul 2>&1
if errorlevel 1 (
    echo %C_RED%[FAIL]%C_RESET% ssh not found. Install OpenSSH Client.
    pause
    goto menu
)
exit /b 0

:pass
echo %C_GREEN%[PASS]%C_RESET% %~1
exit /b 0

:fail
echo %C_RED%[FAIL]%C_RESET% %~1
exit /b 0

:info
echo %C_CYAN%[INFO]%C_RESET% %~1
exit /b 0

:run_public_health
powershell -NoProfile -Command ^
  "try { $r = Invoke-WebRequest -Uri '%PUBLIC_HEALTH_URL%' -UseBasicParsing -TimeoutSec 25 -Headers @{ 'Cache-Control'='no-cache' }; if ($r.StatusCode -eq 200) { Write-Host '[PASS] Health HTTP 200'; exit 0 } else { Write-Host ('[FAIL] Health HTTP ' + $r.StatusCode); exit 1 } } catch { Write-Host ('[FAIL] Health: ' + $_.Exception.Message); exit 1 }"
exit /b %ERRORLEVEL%

:show_deploy_summary
call :init_branch
set "LOCAL_COMMIT="
for /f "delims=" %%C in ('git -C "%ROOT%" rev-parse --short HEAD 2^>nul') do set "LOCAL_COMMIT=%%C"
echo.
echo  %C_BOLD%Deploy Summary%C_RESET%
echo  Branch  : !LOCAL_BRANCH!
echo  Commit  : !LOCAL_COMMIT!
echo  Live    : %PUBLIC_HEALTH_URL%
echo  Time    : %DATE% %TIME%
echo.
exit /b 0

REM =============================================================================
REM 1. Run at local
REM =============================================================================
:run_local
echo.
echo %C_BOLD%[1] Run at local%C_RESET%
cd /d "%ROOT%\erp"
if errorlevel 1 (
    call :fail "erp folder not found"
    pause
    goto menu
)

where python >nul 2>&1
if errorlevel 1 (
    call :fail "Python not found in PATH"
    pause
    cd /d "%ROOT%"
    goto menu
)

if not exist ".venv\Scripts\python.exe" (
    call :info "First run — creating venv and installing requirements..."
    python -m venv .venv
    if errorlevel 1 (
        call :fail "venv create failed"
        pause
        cd /d "%ROOT%"
        goto menu
    )
    call ".venv\Scripts\activate.bat"
    python -m pip install --upgrade pip
    if exist "requirements.txt" python -m pip install -r requirements.txt
    if not exist ".env" if exist ".env.example" copy /Y ".env.example" ".env" >nul
    call :pass "Local install done"
) else (
    call ".venv\Scripts\activate.bat"
)

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do taskkill /PID %%a /F >nul 2>&1
echo.
echo URL: http://localhost:8000/login
echo Press Ctrl+C to stop the server, then any key to return to menu.
echo.
start "" cmd /c "timeout /t 1 /nobreak >nul & start http://localhost:8000/login"
python run.py
cd /d "%ROOT%"
pause
goto menu

REM =============================================================================
REM 2. Push and deploy
REM =============================================================================
:push_and_deploy
call :require_git
call :require_ssh
call :load_vps_env
call :init_branch
echo.
echo %C_BOLD%[2] Push and deploy%C_RESET%
echo.
if /i "!LOCAL_BRANCH!"=="DETACHED" (
    call :fail "Detached HEAD — checkout a branch first"
    pause
    goto menu
)

echo %C_CYAN%Step 1/6%C_RESET% Git status
git -C "%ROOT%" status -sb
echo.

echo %C_CYAN%Step 2/6%C_RESET% Stage all changes
git -C "%ROOT%" add -A
call :pass "Staged"

echo %C_CYAN%Step 3/6%C_RESET% Commit
set "COMMIT_MSG="
set /p COMMIT_MSG="Commit message (Enter = auto): "
if "!COMMIT_MSG!"=="" (
    for /f "tokens=1-3 delims=/ " %%a in ("%date%") do set "D=%%a-%%b-%%c"
    for /f "tokens=1-2 delims=:." %%a in ("%time%") do set "T=%%a%%b"
    set "COMMIT_MSG=deploy !D! !T!"
)
git -C "%ROOT%" diff --cached --quiet
if errorlevel 1 (
    git -C "%ROOT%" commit -m "!COMMIT_MSG!"
    if errorlevel 1 (
        call :fail "Commit failed — abort"
        pause
        goto menu
    )
    call :pass "Committed"
) else (
    call :info "Nothing new to commit"
)

echo %C_CYAN%Step 4/6%C_RESET% Push origin/!LOCAL_BRANCH!
git -C "%ROOT%" push -u origin HEAD
if errorlevel 1 (
    call :fail "Push failed — abort"
    pause
    goto menu
)
call :pass "Push OK"

echo %C_CYAN%Step 5/6%C_RESET% Deploy on VPS ^(deployment/deploy.sh^)
set "DEPLOY_LOG=%LOG_DIR%\deploy_%RANDOM%.log"
echo Enter VPS password when asked.
ssh -p %VPS_PORT% -o StrictHostKeyChecking=accept-new %VPS_USER%@%VPS_HOST% "cd %VPS_PATH% && export BRANCH=%LOCAL_BRANCH% && export VPS_APP_DIR=%VPS_PATH% && export GIT_BRANCH=%LOCAL_BRANCH% && bash deployment/deploy.sh" > "%DEPLOY_LOG%" 2>&1
set "SSH_RC=!ERRORLEVEL!"
type "%DEPLOY_LOG%"
echo.
findstr /C:"===DEPLOY_RESULT:SUCCESS===" "%DEPLOY_LOG%" >nul 2>&1
if errorlevel 1 (
    call :fail "Deploy FAILED — SUCCESS marker not found"
    echo.
    echo --- last 40 lines of deploy log ---
    powershell -NoProfile -Command "Get-Content -LiteralPath '%DEPLOY_LOG%' -Tail 40"
    echo Log: %DEPLOY_LOG%
    pause
    goto menu
)
if not "!SSH_RC!"=="0" (
    call :fail "SSH/deploy exit code !SSH_RC! — FAILED"
    pause
    goto menu
)
call :pass "Deploy script SUCCESS"

echo %C_CYAN%Step 6/6%C_RESET% Public health check
call :run_public_health
if errorlevel 1 (
    call :fail "Health URL not HTTP 200 — deployment FAILED"
    pause
    goto menu
)

call :show_deploy_summary
call :pass "PUSH AND DEPLOY COMPLETE"
echo Log: %DEPLOY_LOG%
pause
goto menu
