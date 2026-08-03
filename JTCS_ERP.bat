@echo off
title JTCS ERP Deployment Console
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
echo  %C_BOLD%JTCS ERP Deployment Console%C_RESET%
echo  %C_CYAN%========================================%C_RESET%
echo  Host   : %VPS_USER%@%VPS_HOST%:%VPS_PORT%
echo  Path   : %VPS_PATH%
echo  Branch : %C_YELLOW%%LOCAL_BRANCH%%C_RESET%
echo  Health : %PUBLIC_HEALTH_URL%
echo  %C_CYAN%========================================%C_RESET%
echo.
echo   1. Git Status
echo   2. Git Add All
echo   3. Commit Changes
echo   4. Push Current Branch
echo   5. Pull Latest
echo   6. Deploy to VPS
echo   7. Restart Application
echo   8. Health Check
echo   9. One Click Push + Deploy
echo  10. Install/Repair VPS Service
echo  11. Show Current VPS Status
echo  12. Show Current Git Branch
echo  13. Show Latest Commit
echo  14. Open Deployment Logs
echo  15. Rollback Previous Version
echo  16. Repair Deployment
echo  17. Full Diagnostics
echo  18. Local Tools (install / start / stop / test / env / schema)
echo  19. Check DB structure Local vs VPS + Update VPS
echo  20. FORCE Live UI Refresh (menus + hard restart)
echo   0. Exit
echo.
set "choice="
set /p choice="Select option (0-20): "
if defined choice set "choice=!choice: =!"

if /i "!choice!"=="1" goto git_status
if /i "!choice!"=="2" goto git_add
if /i "!choice!"=="3" goto git_commit
if /i "!choice!"=="4" goto git_push
if /i "!choice!"=="5" goto git_pull
if /i "!choice!"=="6" goto deploy_vps
if /i "!choice!"=="7" goto restart_app
if /i "!choice!"=="8" goto health_check
if /i "!choice!"=="9" goto oneclick
if /i "!choice!"=="10" goto install_service
if /i "!choice!"=="11" goto vps_status
if /i "!choice!"=="12" goto show_branch
if /i "!choice!"=="13" goto show_commit
if /i "!choice!"=="14" goto open_logs
if /i "!choice!"=="15" goto rollback
if /i "!choice!"=="16" goto repair
if /i "!choice!"=="17" goto diagnostics
if /i "!choice!"=="18" goto local_menu
if /i "!choice!"=="19" goto db_structure_sync
if /i "!choice!"=="20" goto force_ui_refresh
if /i "!choice!"=="L" goto local_menu
if /i "!choice!"=="0" exit /b 0
echo.
echo %C_RED%[FAIL]%C_RESET% Invalid option: "!choice!"
pause
goto menu

REM =============================================================================
REM ENV / HELPERS
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

:ssh_run
REM %~1 = remote command
set "SSH_CMD=%~1"
echo Enter VPS password when asked.
ssh -p %VPS_PORT% -o StrictHostKeyChecking=accept-new %VPS_USER%@%VPS_HOST% "!SSH_CMD!"
exit /b %ERRORLEVEL%

:push_and_sync_vps
REM Push current branch to GitHub, then hard-reset VPS to that branch (keeps erp/.env).
REM Required before remote scripts like install_service.sh exist on the server.
call :require_git
call :require_ssh
call :load_vps_env
call :init_branch
if /i "!LOCAL_BRANCH!"=="DETACHED" (
    call :fail "Detached HEAD ??? checkout a branch first"
    exit /b 1
)
call :info "Syncing branch !LOCAL_BRANCH! ??? GitHub ??? VPS (so new scripts exist)???"
git -C "%ROOT%" add -A
git -C "%ROOT%" diff --cached --quiet
if errorlevel 1 (
    git -C "%ROOT%" commit -m "deploy sync !LOCAL_BRANCH!"
    if errorlevel 1 (
        call :fail "Commit failed during sync"
        exit /b 1
    )
    call :pass "Committed local deploy files"
) else (
    call :info "Nothing new to commit"
)
git -C "%ROOT%" push -u origin HEAD
if errorlevel 1 (
    call :fail "Push failed ??? VPS cannot get new scripts"
    exit /b 1
)
call :pass "Pushed origin/!LOCAL_BRANCH!"
echo Enter VPS password when asked ^(git pull on server^).
ssh -p %VPS_PORT% -o StrictHostKeyChecking=accept-new %VPS_USER%@%VPS_HOST% "cd %VPS_PATH% && ENV_BAK=/tmp/jtcs.env.bak.$$ && if [ -f erp/.env ]; then cp erp/.env $ENV_BAK; fi && git fetch origin %LOCAL_BRANCH% && git checkout -B %LOCAL_BRANCH% origin/%LOCAL_BRANCH% && git reset --hard origin/%LOCAL_BRANCH% && if [ -f $ENV_BAK ]; then cp $ENV_BAK erp/.env; rm -f $ENV_BAK; fi && echo SYNC_OK $(git rev-parse --short HEAD) $(git branch --show-current) && test -f deployment/install_service.sh && test -f deployment/deploy.sh"
if errorlevel 1 (
    call :fail "VPS git sync failed ??? remote scripts still missing"
    exit /b 1
)
call :pass "VPS synced ??? deployment scripts present"
exit /b 0

REM =============================================================================
REM 1-5 GIT
REM =============================================================================
:git_status
call :require_git
call :init_branch
echo.
call :info "Git status (branch=!LOCAL_BRANCH!)"
git -C "%ROOT%" status -sb
echo.
git -C "%ROOT%" log -3 --oneline
pause
goto menu

:git_add
call :require_git
echo.
call :info "git add -A"
git -C "%ROOT%" add -A
if errorlevel 1 (
    call :fail "git add failed"
) else (
    call :pass "Staged all changes"
)
git -C "%ROOT%" status -sb
pause
goto menu

:git_commit
call :require_git
echo.
set "MSG="
set /p MSG="Commit message: "
if "!MSG!"=="" (
    for /f "tokens=1-3 delims=/ " %%a in ("%date%") do set "D=%%a-%%b-%%c"
    for /f "tokens=1-2 delims=:." %%a in ("%time%") do set "T=%%a%%b"
    set "MSG=update !D! !T!"
)
git -C "%ROOT%" add -A
git -C "%ROOT%" diff --cached --quiet
if errorlevel 1 (
    git -C "%ROOT%" commit -m "!MSG!"
    if errorlevel 1 (
        call :fail "Commit failed"
    ) else (
        call :pass "Committed: !MSG!"
    )
) else (
    call :info "Nothing new to commit"
)
pause
goto menu

:git_push
call :require_git
call :init_branch
echo.
call :info "Pushing current branch: !LOCAL_BRANCH!"
if /i "!LOCAL_BRANCH!"=="DETACHED" (
    call :fail "Detached HEAD ??? checkout a branch first"
    pause
    goto menu
)
git -C "%ROOT%" push -u origin HEAD
if errorlevel 1 (
    call :fail "Push failed"
) else (
    call :pass "Push OK ??? origin/!LOCAL_BRANCH!"
)
pause
goto menu

:git_pull
call :require_git
call :init_branch
echo.
call :info "Pull latest for !LOCAL_BRANCH!"
git -C "%ROOT%" pull --ff-only origin "!LOCAL_BRANCH!"
if errorlevel 1 (
    call :fail "Pull failed"
) else (
    call :pass "Pull OK"
)
pause
goto menu

REM =============================================================================
REM 6 Deploy / 9 One-click
REM =============================================================================
:deploy_vps
call :require_git
call :require_ssh
call :load_vps_env
call :init_branch
echo.
echo %C_BOLD%[6] Deploy to VPS%C_RESET%
if /i "!LOCAL_BRANCH!"=="DETACHED" (
    call :fail "Detached HEAD ??? cannot deploy"
    pause
    goto menu
)
call :info "Branch=!LOCAL_BRANCH!  Target=%VPS_USER%@%VPS_HOST%:%VPS_PATH%"
call :info "Canonical script: deployment/deploy.sh (NOT vps_pull_update.sh)"
set "DEPLOY_LOG=%LOG_DIR%\deploy_local_%RANDOM%.log"
echo Enter VPS password when asked.
ssh -p %VPS_PORT% -o StrictHostKeyChecking=accept-new %VPS_USER%@%VPS_HOST% "cd %VPS_PATH% && export BRANCH=%LOCAL_BRANCH% && export VPS_APP_DIR=%VPS_PATH% && export GIT_BRANCH=%LOCAL_BRANCH% && bash deployment/deploy.sh" > "%DEPLOY_LOG%" 2>&1
set "SSH_RC=!ERRORLEVEL!"
type "%DEPLOY_LOG%"
echo.
findstr /C:"===DEPLOY_RESULT:SUCCESS===" "%DEPLOY_LOG%" >nul 2>&1
if errorlevel 1 (
    call :fail "VPS deploy failed or SUCCESS marker missing. See log."
    echo Log: %DEPLOY_LOG%
    pause
    goto menu
)
if not "!SSH_RC!"=="0" (
    call :fail "SSH exited with code !SSH_RC! ??? deployment FAILED"
    pause
    goto menu
)
call :pass "VPS deploy script reported SUCCESS"
call :run_public_health
if errorlevel 1 (
    call :fail "Public health check failed after deploy ??? marked FAILED"
    pause
    goto menu
)
call :show_deploy_summary
pause
goto menu

:oneclick
call :require_git
call :require_ssh
call :load_vps_env
call :init_branch
echo.
echo %C_BOLD%[9] ONE CLICK Push + Deploy%C_RESET%
echo.
if /i "!LOCAL_BRANCH!"=="DETACHED" (
    call :fail "Detached HEAD ??? checkout a branch first"
    pause
    goto menu
)

echo %C_CYAN%Step 1/10%C_RESET% Git Status
git -C "%ROOT%" status -sb
echo.

echo %C_CYAN%Step 2/10%C_RESET% Git Add
git -C "%ROOT%" add -A
call :pass "Staged"

echo %C_CYAN%Step 3/10%C_RESET% Commit
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
        call :fail "Commit failed ??? abort"
        pause
        goto menu
    )
    call :pass "Committed"
) else (
    call :info "Nothing new to commit"
)

echo %C_CYAN%Step 4/10%C_RESET% Detect current branch
call :init_branch
call :pass "Current branch = !LOCAL_BRANCH!"

echo %C_CYAN%Step 5/10%C_RESET% Push origin HEAD
git -C "%ROOT%" push -u origin HEAD
if errorlevel 1 (
    call :fail "Push failed ??? abort"
    pause
    goto menu
)
call :pass "Push OK"

echo %C_CYAN%Step 6-7/10%C_RESET% SSH + deployment/deploy.sh
set "DEPLOY_LOG=%LOG_DIR%\oneclick_%RANDOM%.log"
echo Enter VPS password when asked.
ssh -p %VPS_PORT% -o StrictHostKeyChecking=accept-new %VPS_USER%@%VPS_HOST% "cd %VPS_PATH% && export BRANCH=%LOCAL_BRANCH% && export VPS_APP_DIR=%VPS_PATH% && export GIT_BRANCH=%LOCAL_BRANCH% && bash deployment/deploy.sh" > "%DEPLOY_LOG%" 2>&1
set "SSH_RC=!ERRORLEVEL!"
type "%DEPLOY_LOG%"
echo.

echo %C_CYAN%Step 8/10%C_RESET% Read deployment result
findstr /C:"===DEPLOY_RESULT:SUCCESS===" "%DEPLOY_LOG%" >nul 2>&1
if errorlevel 1 (
    call :fail "Deploy FAILED ??? SUCCESS marker not found"
    echo.
    echo --- last 40 lines of deploy log ---
    powershell -NoProfile -Command "Get-Content -LiteralPath '%DEPLOY_LOG%' -Tail 40"
    pause
    goto menu
)
if not "!SSH_RC!"=="0" (
    call :fail "SSH/deploy exit code !SSH_RC! ??? FAILED"
    pause
    goto menu
)
call :pass "Deploy script SUCCESS"

echo %C_CYAN%Step 9/10%C_RESET% Public health %PUBLIC_HEALTH_URL%
call :run_public_health
if errorlevel 1 (
    call :fail "Health URL not HTTP 200 ??? deployment FAILED"
    pause
    goto menu
)

echo %C_CYAN%Step 10/10%C_RESET% Summary
call :show_deploy_summary
echo.
call :pass "ONE CLICK DEPLOY COMPLETE"
echo Log: %DEPLOY_LOG%
pause
goto menu

:run_public_health
powershell -NoProfile -Command ^
  "try { $r = Invoke-WebRequest -Uri '%PUBLIC_HEALTH_URL%' -UseBasicParsing -TimeoutSec 25 -Headers @{ 'Cache-Control'='no-cache' }; if ($r.StatusCode -eq 200) { Write-Host '[PASS] Health HTTP 200'; exit 0 } else { Write-Host ('[FAIL] Health HTTP ' + $r.StatusCode); exit 1 } } catch { Write-Host ('[FAIL] Health: ' + $_.Exception.Message); exit 1 }"
exit /b %ERRORLEVEL%

:show_deploy_summary
call :init_branch
set "LOCAL_COMMIT="
for /f "delims=" %%C in ('git -C "%ROOT%" rev-parse --short HEAD 2^>nul') do set "LOCAL_COMMIT=%%C"
echo.
echo  %C_CYAN%========================================%C_RESET%
echo  %C_BOLD%Deployment Summary%C_RESET%
echo  %C_CYAN%========================================%C_RESET%
echo  Branch     : !LOCAL_BRANCH!
echo  Commit     : !LOCAL_COMMIT!
echo  App URL    : https://app.jtcsxpert.com
echo  Health URL : %PUBLIC_HEALTH_URL%
echo  Deployed   : %DATE% %TIME%
echo  %C_CYAN%========================================%C_RESET%
exit /b 0

REM =============================================================================
REM 7 Restart / 8 Health / 10 Service / 11 Status
REM =============================================================================
:restart_app
echo.
call :info "Restarting jtcs-erp on VPS???"
call :push_and_sync_vps
if errorlevel 1 (
    pause
    goto menu
)
echo Enter VPS password when asked ^(service restart^).
ssh -p %VPS_PORT% -o StrictHostKeyChecking=accept-new %VPS_USER%@%VPS_HOST% "cd %VPS_PATH% && export VPS_APP_DIR=%VPS_PATH% && bash deployment/install_service.sh"
if errorlevel 1 (
    call :fail "Restart/service repair FAILED"
) else (
    call :pass "Service restart OK"
    call :run_public_health
)
pause
goto menu

:health_check
call :load_vps_env
echo.
call :info "Local public health check???"
call :run_public_health
echo.
call :info "VPS local health + service???"
call :push_and_sync_vps
if errorlevel 1 (
    pause
    goto menu
)
echo Enter VPS password when asked.
ssh -p %VPS_PORT% -o StrictHostKeyChecking=accept-new %VPS_USER%@%VPS_HOST% "cd %VPS_PATH% && export VPS_APP_DIR=%VPS_PATH% && bash deployment/healthcheck.sh"
pause
goto menu

:install_service
echo.
echo %C_BOLD%[10] Install/Repair VPS Service%C_RESET%
echo.
call :info "New scripts must be on VPS first ??? pushing + syncing???"
call :push_and_sync_vps
if errorlevel 1 (
    pause
    goto menu
)
call :info "Installing systemd unit (gunicorn wsgi:app)???"
echo Enter VPS password when asked ^(service install^).
ssh -p %VPS_PORT% -o StrictHostKeyChecking=accept-new %VPS_USER%@%VPS_HOST% "cd %VPS_PATH% && export VPS_APP_DIR=%VPS_PATH% && bash deployment/install_service.sh"
if errorlevel 1 (
    call :fail "Service install FAILED"
) else (
    call :pass "Service install/repair OK"
    call :run_public_health
)
pause
goto menu

:vps_status
echo.
call :push_and_sync_vps
if errorlevel 1 (
    pause
    goto menu
)
echo Enter VPS password when asked.
ssh -p %VPS_PORT% -o StrictHostKeyChecking=accept-new %VPS_USER%@%VPS_HOST% "cd %VPS_PATH% && export VPS_APP_DIR=%VPS_PATH% && bash deployment/vps_status.sh"
pause
goto menu

:show_branch
call :require_git
call :init_branch
echo.
call :pass "Local branch: !LOCAL_BRANCH!"
git -C "%ROOT%" branch -vv
pause
goto menu

:show_commit
call :require_git
echo.
git -C "%ROOT%" log -1 --format=fuller
echo.
git -C "%ROOT%" rev-parse HEAD
pause
goto menu

:open_logs
echo.
call :info "Opening local deployment logs: %LOG_DIR%"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1
start "" explorer "%LOG_DIR%"
echo.
call :info "Also on VPS: /var/log/jtcs-erp/"
call :require_ssh
call :ssh_run "ls -lt /var/log/jtcs-erp 2>/dev/null | head -20; echo; echo '--- history ---'; tail -n 40 /var/log/jtcs-erp/deploy_history.log 2>/dev/null || echo '(no history yet)'"
pause
goto menu

:rollback
echo.
echo %C_YELLOW%WARNING:%C_RESET% Rollback restores previous app files. SQL data is NOT overwritten by default.
set "CONFIRM="
set /p CONFIRM="Type YES to rollback latest backup: "
if /i not "!CONFIRM!"=="YES" (
    call :info "Rollback cancelled"
    pause
    goto menu
)
call :push_and_sync_vps
if errorlevel 1 (
    pause
    goto menu
)
echo Enter VPS password when asked.
ssh -p %VPS_PORT% -o StrictHostKeyChecking=accept-new %VPS_USER%@%VPS_HOST% "cd %VPS_PATH% && export VPS_APP_DIR=%VPS_PATH% && bash deployment/rollback.sh --latest --reason manual-bat"
if errorlevel 1 (
    call :fail "Rollback FAILED"
) else (
    call :pass "Rollback finished"
    call :run_public_health
)
pause
goto menu

:repair
echo.
call :info "Repair deployment on VPS???"
call :push_and_sync_vps
if errorlevel 1 (
    pause
    goto menu
)
echo Enter VPS password when asked.
ssh -p %VPS_PORT% -o StrictHostKeyChecking=accept-new %VPS_USER%@%VPS_HOST% "cd %VPS_PATH% && export BRANCH=%LOCAL_BRANCH% && export VPS_APP_DIR=%VPS_PATH% && export GIT_BRANCH=%LOCAL_BRANCH% && bash deployment/repair.sh"
if errorlevel 1 (
    call :fail "Repair FAILED"
) else (
    call :pass "Repair OK"
    call :run_public_health
)
pause
goto menu

:diagnostics
echo.
echo %C_BOLD%[17] Full Diagnostics%C_RESET%
echo.
call :init_branch
call :info "--- LOCAL ---"
where git >nul 2>&1 && (call :pass "Git") || (call :fail "Git")
where ssh >nul 2>&1 && (call :pass "SSH") || (call :fail "SSH")
call :pass "Branch !LOCAL_BRANCH!"
for /f "delims=" %%C in ('git -C "%ROOT%" rev-parse --short HEAD 2^>nul') do call :pass "Commit %%C"
call :run_public_health
echo.
call :info "--- VPS ---"
call :push_and_sync_vps
if errorlevel 1 (
    pause
    goto menu
)
echo Enter VPS password when asked.
ssh -p %VPS_PORT% -o StrictHostKeyChecking=accept-new %VPS_USER%@%VPS_HOST% "cd %VPS_PATH% && export VPS_APP_DIR=%VPS_PATH% && bash deployment/diagnostics.sh"
pause
goto menu

:db_structure_sync
echo.
echo %C_BOLD%[19] Check DB structure Local vs VPS + Update VPS%C_RESET%
echo.
echo  %C_YELLOW%Policy:%C_RESET% SCHEMA only — tables/columns. SQL DATA is never copied or wiped.
echo.
call :require_git
call :require_ssh
call :load_vps_env
call :init_branch

if not exist "%ROOT%\erp\.venv\Scripts\python.exe" (
    call :fail "Local venv missing — run option 18 then Install first"
    pause
    goto menu
)
where scp >nul 2>&1
if errorlevel 1 (
    call :fail "scp not found. Install OpenSSH Client."
    pause
    goto menu
)

set "SCHEMA_DUMP=%LOG_DIR%\schema_local_%RANDOM%.json"
set "SCHEMA_LOG=%LOG_DIR%\schema_sync_%RANDOM%.log"

echo %C_CYAN%Step 1/5%C_RESET% Dump LOCAL database structure
cd /d "%ROOT%\erp"
".venv\Scripts\python.exe" scripts\compare_and_sync_schema.py --dump "%SCHEMA_DUMP%"
if errorlevel 1 (
    call :fail "Local schema dump failed — check erp\.env DB settings"
    cd /d "%ROOT%"
    pause
    goto menu
)
call :pass "Local schema dumped"
cd /d "%ROOT%"

echo %C_CYAN%Step 2/5%C_RESET% Push + sync code to VPS (migrations/scripts)
call :push_and_sync_vps
if errorlevel 1 (
    pause
    goto menu
)

echo %C_CYAN%Step 3/5%C_RESET% Upload schema dump to VPS
echo Enter VPS password when asked ^(scp^).
scp -P %VPS_PORT% -o StrictHostKeyChecking=accept-new "%SCHEMA_DUMP%" %VPS_USER%@%VPS_HOST%:/tmp/jtcs_schema_local.json
if errorlevel 1 (
    call :fail "scp upload failed"
    pause
    goto menu
)
call :pass "Dump uploaded to /tmp/jtcs_schema_local.json"

echo %C_CYAN%Step 4/5%C_RESET% Apply numbered migrations on VPS
echo Enter VPS password when asked ^(migrations^).
ssh -p %VPS_PORT% -o StrictHostKeyChecking=accept-new %VPS_USER%@%VPS_HOST% "cd %VPS_PATH%/erp && if [ -x .venv/bin/python ]; then .venv/bin/python scripts/apply_schema_migrations.py; else python3 scripts/apply_schema_migrations.py; fi" > "%SCHEMA_LOG%" 2>&1
set "MIG_RC=!ERRORLEVEL!"
type "%SCHEMA_LOG%"
echo.
if not "!MIG_RC!"=="0" (
    call :fail "VPS migrations reported errors — continuing to column sync"
) else (
    call :pass "VPS migrations OK"
)

echo %C_CYAN%Step 5/5%C_RESET% Compare Local dump vs VPS DB + add missing columns
set "SYNC_OUT=%LOG_DIR%\schema_sync_out_%RANDOM%.log"
echo Enter VPS password when asked ^(schema sync^).
ssh -p %VPS_PORT% -o StrictHostKeyChecking=accept-new %VPS_USER%@%VPS_HOST% "cd %VPS_PATH%/erp && if [ -x .venv/bin/python ]; then .venv/bin/python scripts/compare_and_sync_schema.py --sync-from /tmp/jtcs_schema_local.json; else python3 scripts/compare_and_sync_schema.py --sync-from /tmp/jtcs_schema_local.json; fi" > "%SYNC_OUT%" 2>&1
set "SYNC_RC=!ERRORLEVEL!"
type "%SYNC_OUT%"
type "%SYNC_OUT%" >> "%SCHEMA_LOG%"
echo.
if "!SYNC_RC!"=="0" (
    call :pass "DB structure sync COMPLETE — VPS columns match local"
) else if "!SYNC_RC!"=="2" (
    call :fail "Some tables still missing on VPS — run option 9 then re-run 19"
) else (
    call :fail "Schema sync finished with errors — see log"
)
echo Dump: %SCHEMA_DUMP%
echo Log : %SCHEMA_LOG%
pause
goto menu

:force_ui_refresh
echo.
echo %C_BOLD%[20] FORCE Live UI Refresh%C_RESET%
echo.
echo  Ye option:
echo   - latest code push/sync
echo   - MenuMaster core nav + eCourt ensure
echo   - gunicorn HARD kill + restart (purana UI hataata hai)
echo.
call :require_git
call :require_ssh
call :load_vps_env
call :init_branch
if /i "!LOCAL_BRANCH!"=="DETACHED" (
    call :fail "Detached HEAD — checkout a branch first"
    pause
    goto menu
)

echo %C_CYAN%Step 1/3%C_RESET% Push local changes
git -C "%ROOT%" add -A
git -C "%ROOT%" diff --cached --quiet
if errorlevel 1 (
    git -C "%ROOT%" commit -m "force ui refresh !LOCAL_BRANCH!"
    if errorlevel 1 (
        call :fail "Commit failed"
        pause
        goto menu
    )
)
git -C "%ROOT%" push -u origin HEAD
if errorlevel 1 (
    call :fail "Push failed"
    pause
    goto menu
)
call :pass "Pushed origin/!LOCAL_BRANCH!"

echo %C_CYAN%Step 2/3%C_RESET% VPS force_ui_refresh.sh
set "UI_LOG=%LOG_DIR%\ui_refresh_%RANDOM%.log"
echo Enter VPS password when asked.
ssh -p %VPS_PORT% -o StrictHostKeyChecking=accept-new %VPS_USER%@%VPS_HOST% "cd %VPS_PATH% && export BRANCH=%LOCAL_BRANCH% && export VPS_APP_DIR=%VPS_PATH% && export GIT_BRANCH=%LOCAL_BRANCH% && bash deployment/force_ui_refresh.sh" > "%UI_LOG%" 2>&1
set "UI_RC=!ERRORLEVEL!"
type "%UI_LOG%"
echo.

echo %C_CYAN%Step 3/3%C_RESET% Verify
findstr /C:"===UI_REFRESH:SUCCESS===" "%UI_LOG%" >nul 2>&1
if errorlevel 1 (
    call :fail "UI refresh FAILED — see log"
    echo Log: %UI_LOG%
    pause
    goto menu
)
if not "!UI_RC!"=="0" (
    call :fail "SSH exit code !UI_RC!"
    pause
    goto menu
)
call :pass "UI refresh SUCCESS on VPS"
call :run_public_health
echo.
echo Ab browser me:
echo   1. https://app.jtcsxpert.com
echo   2. Ctrl+F5
echo   3. Logout + Login
echo Top menu me ITR/GST/Payroll NAHI dikhne chahiye.
echo Activities me eCourt Activity dikhna chahiye.
pause
goto menu

REM =============================================================================
REM LOCAL TOOLS (preserved)
REM =============================================================================
:local_menu
cls
echo.
echo  %C_CYAN%========================================%C_RESET%
echo  %C_BOLD%Local Development Tools%C_RESET%
echo  %C_CYAN%========================================%C_RESET%
echo.
echo   1. Install (first time / repair venv)
echo   2. Start local server
echo   3. Stop local server
echo   4. Run auth tests
echo   5. Open local login page
echo   6. Edit erp\.env
echo   D. Database SCHEMA update only (local)
echo   0. Back to main menu
echo.
set "lchoice="
set /p lchoice="Select: "
if defined lchoice set "lchoice=!lchoice: =!"
if /i "!lchoice!"=="1" goto local_install
if /i "!lchoice!"=="2" goto local_start
if /i "!lchoice!"=="3" goto local_stop
if /i "!lchoice!"=="4" goto local_test
if /i "!lchoice!"=="5" goto local_browser
if /i "!lchoice!"=="6" goto local_env
if /i "!lchoice!"=="D" goto local_schema
if /i "!lchoice!"=="0" goto menu
goto local_menu

:local_install
echo.
call :info "Creating venv and installing requirements???"
cd /d "%ROOT%\erp"
if errorlevel 1 (
    call :fail "erp folder not found"
    pause
    goto local_menu
)
where python >nul 2>&1
if errorlevel 1 (
    call :fail "Python not found"
    pause
    cd /d "%ROOT%"
    goto local_menu
)
if not exist ".venv\Scripts\python.exe" python -m venv .venv
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
if exist "requirements.txt" python -m pip install -r requirements.txt
if not exist ".env" if exist ".env.example" copy /Y ".env.example" ".env" >nul
call :pass "Local install done"
pause
cd /d "%ROOT%"
goto local_menu

:local_start
echo.
cd /d "%ROOT%\erp"
if not exist ".venv\Scripts\activate.bat" (
    call :fail "venv missing ??? run Local Install first"
    pause
    cd /d "%ROOT%"
    goto local_menu
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do taskkill /PID %%a /F >nul 2>&1
call ".venv\Scripts\activate.bat"
echo URL: http://localhost:8000/login
echo Press Ctrl+C to stop.
start "" cmd /c "timeout /t 1 /nobreak >nul & start http://localhost:8000/login"
REM Local boot helper (Windows only). Production VPS uses gunicorn wsgi:app.
python run.py
cd /d "%ROOT%"
goto local_menu

:local_stop
echo.
call :info "Stopping local listeners on :8000"
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    echo Killing PID %%a
    taskkill /PID %%a /F >nul 2>&1
)
call :pass "Done"
pause
goto local_menu

:local_test
cd /d "%ROOT%\erp"
if not exist ".venv\Scripts\activate.bat" (
    call :fail "venv missing"
    pause
    cd /d "%ROOT%"
    goto local_menu
)
call ".venv\Scripts\activate.bat"
python scripts\test_auth.py
pause
cd /d "%ROOT%"
goto local_menu

:local_browser
start "" "http://localhost:8000/login"
goto local_menu

:local_env
if not exist "%ROOT%\erp\.env" if exist "%ROOT%\erp\.env.example" copy /Y "%ROOT%\erp\.env.example" "%ROOT%\erp\.env" >nul
notepad "%ROOT%\erp\.env"
goto local_menu

:local_schema
echo.
call :info "Schema-only DB update (DATA safe)???"
cd /d "%ROOT%\erp"
if not exist ".venv\Scripts\python.exe" (
    call :fail "venv missing"
    pause
    cd /d "%ROOT%"
    goto local_menu
)
".venv\Scripts\python.exe" scripts\apply_schema_migrations.py
if errorlevel 1 (
    call :fail "Schema update failed ??? data not overwritten"
) else (
    call :pass "Schema update OK"
)
pause
cd /d "%ROOT%"
goto local_menu

