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

REM --- GitHub Repository ---
set "GIT_REPO_URL=https://github.com/rj22884/JTCS-Final.git"
set "GIT_REPO_HTTPS=https://github.com/rj22884/JTCS-Final"

call :load_vps_env
call :init_branch
call :ensure_git_remote

REM ============================================================================
REM COMMAND LINE OPTIONS
REM JTCS_ERP.bat 0
REM JTCS_ERP.bat 1
REM JTCS_ERP.bat 2
REM JTCS_ERP.bat local
REM JTCS_ERP.bat deploy
REM ============================================================================

if not "%~1"=="" (
    set "choice=%~1"

    if /i "!choice!"=="local" set "choice=1"
    if /i "!choice!"=="deploy" set "choice=2"

    if /i "!choice!"=="0" goto stop_and_exit
    if /i "!choice!"=="1" goto run_local
    if /i "!choice!"=="2" goto push_and_deploy
)

REM ============================================================================
REM MAIN MENU
REM ============================================================================

:menu
cls

echo.
echo  %C_CYAN%========================================%C_RESET%
echo  %C_BOLD%JTCS ERP%C_RESET%
echo  %C_CYAN%========================================%C_RESET%
echo  Branch : %C_YELLOW%%LOCAL_BRANCH%%C_RESET%
echo  GitHub : %GIT_REPO_HTTPS%
echo  Live   : %PUBLIC_HEALTH_URL%
echo  Local  : http://localhost:8000
echo  VPS    : %VPS_USER%@%VPS_HOST%:%VPS_PATH%
echo  %C_CYAN%========================================%C_RESET%
echo.
echo   1. Run at local
echo   2. Push and deploy
echo   0. Stop and Exit
echo.

set "choice="
set /p choice="Select option (0-2): "

if defined choice set "choice=!choice: =!"

if /i "!choice!"=="0" goto stop_and_exit
if /i "!choice!"=="1" goto run_local
if /i "!choice!"=="2" goto push_and_deploy

echo.
echo %C_RED%[FAIL]%C_RESET% Invalid option: "!choice!"
pause
goto menu


REM ============================================================================
REM 0. STOP AND EXIT
REM ============================================================================
:stop_and_exit

cls

echo.
echo %C_CYAN%========================================%C_RESET%
echo %C_BOLD%JTCS ERP - STOP AND EXIT%C_RESET%
echo %C_CYAN%========================================%C_RESET%
echo.

echo %C_YELLOW%Stopping JTCS ERP on port 8000...%C_RESET%
echo.

REM --------------------------------------------------------------------------
REM Find every process listening on TCP port 8000
REM and terminate it.
REM --------------------------------------------------------------------------

set "FOUND_8000="

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    set "FOUND_8000=1"
    echo Stopping PID %%a...
    taskkill /PID %%a /T /F >nul 2>&1

    if errorlevel 1 (
        echo %C_RED%[FAIL]%C_RESET% Could not stop PID %%a
    ) else (
        echo %C_GREEN%[PASS]%C_RESET% PID %%a stopped.
    )
)

REM --------------------------------------------------------------------------
REM Give Windows a moment to release the port
REM --------------------------------------------------------------------------

timeout /t 1 /nobreak >nul

echo.
echo %C_CYAN%Checking port 8000...%C_RESET%
echo.

REM --------------------------------------------------------------------------
REM Verify port 8000
REM --------------------------------------------------------------------------

netstat -ano | findstr ":8000 " | findstr "LISTENING" >nul 2>&1

if errorlevel 1 (

    if defined FOUND_8000 (
        echo %C_GREEN%[PASS]%C_RESET% Port 8000 successfully cleared.
    ) else (
        echo %C_GREEN%[INFO]%C_RESET% Port 8000 was already free.
    )

) else (

    echo %C_RED%[FAIL]%C_RESET% Port 8000 is still in use.
    echo.
    echo Please check the process manually using:
    echo.
    echo netstat -ano ^| findstr :8000
    echo.
)

echo.
echo %C_GREEN%JTCS ERP stopped.%C_RESET%
echo.
echo %C_YELLOW%Exiting...%C_RESET%

timeout /t 2 /nobreak >nul

exit /b 0


REM ============================================================================
REM HELPERS
REM ============================================================================

:load_vps_env

set "VPS_HOST=200.234.41.220"
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


:ensure_git_remote

REM Point origin at the new GitHub repo

git -C "%ROOT%" remote get-url origin >nul 2>&1

if errorlevel 1 (

    git -C "%ROOT%" remote add origin "%GIT_REPO_URL%" >nul 2>&1

) else (

    git -C "%ROOT%" remote set-url origin "%GIT_REPO_URL%" >nul 2>&1

)

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


:judge_remote_deploy

REM Args:
REM %1 = log file
REM %2 = ssh exit code

set "JD_LOG=%~1"
set "JD_RC=%~2"

if not exist "!JD_LOG!" (

    call :fail "Deploy log missing"
    exit /b 1

)

powershell -NoProfile -Command "$p='!JD_LOG!'; $rc='!JD_RC!'; try { $t = Get-Content -LiteralPath $p -Raw -ErrorAction Stop } catch { Write-Host ('[FAIL] Cannot read log: ' + $_.Exception.Message); exit 1 }; $ok = $t -match 'DEPLOY_RESULT:SUCCESS|FULL_OVERWRITE:SUCCESS|DEPLOYMENT SUCCESS'; $bad = $t -match 'DEPLOY_RESULT:FAILED|DEPLOY_RESULT:Failed|FULL_OVERWRITE:FAILED'; if ($bad -and -not $ok) { Write-Host '[FAIL] Remote reported FAILED'; $m = [regex]::Match($t, 'ABORT:\s*(.+)'); if ($m.Success) { Write-Host ('[FAIL] ' + $m.Groups[1].Value.Trim()) }; $m2 = [regex]::Match($t, '\[ERROR\]\s*(.+)'); if ($m2.Success) { Write-Host ('[FAIL] ' + $m2.Groups[1].Value.Trim()) }; exit 1 }; if ($ok) { Write-Host '[PASS] SUCCESS marker found in log'; exit 0 }; if ($rc -eq '0') { Write-Host '[INFO] SUCCESS marker missing in captured log - SSH exit 0, continuing to health check'; exit 0 }; Write-Host ('[FAIL] Remote failed (SSH exit ' + $rc + ')'); exit 1"

if errorlevel 1 exit /b 1

exit /b 0


:show_deploy_summary

call :init_branch

set "LOCAL_COMMIT="

for /f "delims=" %%C in ('git -C "%ROOT%" rev-parse --short HEAD 2^>nul') do set "LOCAL_COMMIT=%%C"

echo.
echo %C_BOLD%Deploy Summary%C_RESET%
echo Branch  : !LOCAL_BRANCH!
echo Commit  : !LOCAL_COMMIT!
echo GitHub  : %GIT_REPO_HTTPS%
echo Live    : %PUBLIC_HEALTH_URL%
echo Time    : %DATE% %TIME%
echo.

exit /b 0


:clear_git_lock

REM Remove stale .git/index.lock

if not exist "%ROOT%\.git\index.lock" exit /b 0

call :info "Found .git\index.lock - clearing stale lock..."

del /f /q "%ROOT%\.git\index.lock" >nul 2>&1

if exist "%ROOT%\.git\index.lock" (

    call :fail "Could not delete .git\index.lock - close other git/Cursor git ops and retry"
    exit /b 1

)

call :pass "Cleared stale index.lock"

exit /b 0


:git_commit_push

REM Shared: stage, commit, push current branch

call :ensure_git_remote
call :init_branch

if /i "!LOCAL_BRANCH!"=="DETACHED" (

    call :fail "Detached HEAD - checkout a branch first"
    exit /b 1

)

call :clear_git_lock

if errorlevel 1 exit /b 1

echo %C_CYAN%Git%C_RESET% status

git -C "%ROOT%" status -sb

echo.
echo %C_CYAN%Git%C_RESET% remote origin

git -C "%ROOT%" remote -v

echo.
echo %C_CYAN%Git%C_RESET% stage all

git -C "%ROOT%" add -A

if errorlevel 1 (

    call :clear_git_lock

    if errorlevel 1 exit /b 1

    git -C "%ROOT%" add -A

    if errorlevel 1 (

        call :fail "git add failed - is .git\index.lock stuck?"
        exit /b 1

    )

)

call :pass "Staged"

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

        call :fail "Commit failed"
        exit /b 1

    )

    call :pass "Committed"

) else (

    call :info "Nothing new to commit"

)

echo %C_CYAN%Git%C_RESET% push origin/!LOCAL_BRANCH! -^> %GIT_REPO_URL%

git -C "%ROOT%" push -u origin HEAD

if errorlevel 1 (

    call :fail "Push failed - check GitHub auth / repo access"
    exit /b 1

)

call :pass "Push OK to %GIT_REPO_HTTPS%"

exit /b 0


REM ============================================================================
REM 1. RUN AT LOCAL
REM ============================================================================

:run_local

echo.
echo %C_BOLD%[1] Run at local%C_RESET%

if exist "%ROOT%\scripts\run_local_auto_backup_watch.bat" (

    call "%ROOT%\scripts\run_local_auto_backup_watch.bat"

    call :info "Auto-backup: D:\JTCS Backup\Auto"

)

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

    call :info "First run - creating venv and installing requirements..."

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

REM --------------------------------------------------------------------------
REM Before starting local server, clear port 8000
REM --------------------------------------------------------------------------

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /T /F >nul 2>&1
)

echo.
echo URL: http://localhost:8000/login
echo Press Ctrl+C to stop the server, then any key to return to menu.
echo.

start "" cmd /c "timeout /t 1 /nobreak >nul & start http://localhost:8000/login"

python run.py

cd /d "%ROOT%"

pause

goto menu


REM ============================================================================
REM 2. PUSH AND DEPLOY
REM ============================================================================

:push_and_deploy

call :require_git
call :require_ssh
call :load_vps_env
call :init_branch

echo.
echo %C_BOLD%[2] Push and deploy%C_RESET%
echo Repo : %GIT_REPO_URL%
echo Mode : normal deploy (deployment/deploy.sh)
echo.

call :git_commit_push

if errorlevel 1 (
    pause
    goto menu
)

echo %C_CYAN%Deploy%C_RESET% on VPS (deployment/deploy.sh)

set "DEPLOY_LOG=%LOG_DIR%\deploy_%RANDOM%.log"

echo Enter VPS password when asked.

ssh -p %VPS_PORT% -o StrictHostKeyChecking=accept-new %VPS_USER%@%VPS_HOST% "cd %VPS_PATH% && git remote set-url origin %GIT_REPO_URL% && export BRANCH=%LOCAL_BRANCH% && export VPS_APP_DIR=%VPS_PATH% && export GIT_BRANCH=%LOCAL_BRANCH% && bash deployment/deploy.sh && echo ===DEPLOY_RESULT:SUCCESS===" > "%DEPLOY_LOG%" 2>&1

set "SSH_RC=!ERRORLEVEL!"

type "%DEPLOY_LOG%"

echo.

call :judge_remote_deploy "%DEPLOY_LOG%" "!SSH_RC!"

if errorlevel 1 (

    echo.
    echo --- last 40 lines of deploy log ---

    powershell -NoProfile -Command "Get-Content -LiteralPath '%DEPLOY_LOG%' -Tail 40"

    echo Log: %DEPLOY_LOG%

    pause

    goto menu

)

call :pass "Deploy script SUCCESS"

call :run_public_health

if errorlevel 1 (

    call :fail "Health URL not HTTP 200 - deployment FAILED"

    pause

    goto menu

)

call :show_deploy_summary

call :pass "PUSH AND DEPLOY COMPLETE"

echo Log: %DEPLOY_LOG%

pause

goto menu