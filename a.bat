@echo off
title JTCS ERP - Launcher
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

:menu
cls
echo.
echo  ============================================
echo    JTCS ERP - Joshi Tax Consultancy
echo  ============================================
echo.
echo    1. Install (first time only)
echo    2. Start server
echo    3. Stop server
echo    4. Run auth tests
echo    5. Open login page in browser
echo    6. Edit .env settings
echo    7. Push code to GitHub
echo    8. Deploy to VPS (git pull on server)
echo    9. ONE CLICK: Push + Deploy VPS
echo       (code + schema only - SQL DATA safe)
echo    D. Database SCHEMA update only (local)
echo       (new tables/columns only - DATA safe)
echo    0. Exit
echo.
set "choice="
set /p choice="Select option (0-9 / D): "
if defined choice set "choice=!choice: =!"

if /i "!choice!"=="1" goto install
if /i "!choice!"=="2" goto start
if /i "!choice!"=="3" goto stop
if /i "!choice!"=="4" goto test
if /i "!choice!"=="5" goto browser
if /i "!choice!"=="6" goto editenv
if /i "!choice!"=="7" goto pushgit
if /i "!choice!"=="8" goto deployvps
if /i "!choice!"=="9" goto oneclick
if /i "!choice!"=="D" goto dbschema
if /i "!choice!"=="0" exit /b 0
echo.
echo Invalid option: "!choice!"
pause
goto menu

:install
echo.
echo [1] Install - creating venv and installing requirements...
cd /d "%~dp0erp"
if errorlevel 1 (
    echo ERROR: erp folder not found.
    pause
    goto menu
)
where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH.
    pause
    cd /d "%~dp0"
    goto menu
)
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
if exist "requirements.txt" (
    python -m pip install -r requirements.txt
)
if not exist ".env" (
    if exist ".env.example" copy /Y ".env.example" ".env" >nul
    echo Created erp\.env - edit MAIL_PASSWORD if needed.
)
echo.
echo Install done. Use option 2 to start server.
pause
cd /d "%~dp0"
goto menu

:start
echo.
echo [2] Starting JTCS ERP...
cd /d "%~dp0erp"
if errorlevel 1 (
    echo ERROR: erp folder not found.
    pause
    goto menu
)
if not exist ".venv\Scripts\activate.bat" (
    echo ERROR: venv missing. Run option 1 first.
    pause
    cd /d "%~dp0"
    goto menu
)
REM stop old listener on 8000
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
call ".venv\Scripts\activate.bat"
echo URL: http://localhost:8000/login
echo Press Ctrl+C to stop.
echo.
start "" cmd /c "timeout /t 1 /nobreak >nul & start http://localhost:8000/login"
python run.py
if errorlevel 1 (
    echo Server stopped with an error.
    pause
)
cd /d "%~dp0"
goto menu

:stop
echo.
echo [3] Stopping server on port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    echo Killing PID %%a
    taskkill /PID %%a /F >nul 2>&1
)
echo Done.
pause
goto menu

:test
echo.
echo [4] Auth tests...
cd /d "%~dp0erp"
if not exist ".venv\Scripts\activate.bat" (
    echo ERROR: venv missing. Run option 1 first.
    pause
    cd /d "%~dp0"
    goto menu
)
call ".venv\Scripts\activate.bat"
python scripts\test_auth.py
echo.
pause
cd /d "%~dp0"
goto menu

:browser
start "" "http://localhost:8000/login"
goto menu

:editenv
if not exist "%~dp0erp\.env" (
    if exist "%~dp0erp\.env.example" copy /Y "%~dp0erp\.env.example" "%~dp0erp\.env" >nul
)
notepad "%~dp0erp\.env"
goto menu

:pushgit
echo.
echo [7] Push to GitHub...
cd /d "%~dp0"
where git >nul 2>&1
if errorlevel 1 (
    echo ERROR: git not found.
    pause
    goto menu
)
git status -sb
echo.
set "MSG="
set /p MSG="Commit message (Enter = auto): "
if "!MSG!"=="" (
    for /f "tokens=1-3 delims=/ " %%a in ("%date%") do set "D=%%a-%%b-%%c"
    for /f "tokens=1-2 delims=:." %%a in ("%time%") do set "T=%%a%%b"
    set "MSG=update !D! !T!"
)
git add -A
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "!MSG!"
    if errorlevel 1 (
        echo Commit failed.
        pause
        goto menu
    )
) else (
    echo Nothing new to commit.
)
git push -u origin HEAD
if errorlevel 1 (
    echo Push failed.
    pause
    goto menu
)
echo Push OK.
pause
goto menu

:deployvps
echo.
echo [8] Deploy to VPS...
cd /d "%~dp0"
set "VPS_HOST=200.141.5.68"
set "VPS_USER=root"
set "VPS_PORT=22"
set "VPS_PATH=/root/JTCS-final"
if exist "deploy_vps.env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in (`powershell -NoProfile -Command "Get-Content -LiteralPath 'deploy_vps.env' | ForEach-Object { $_ -replace '`r','' }"`) do (
        if not "%%A"=="" set "%%A=%%B"
    )
)
if /i "!VPS_PATH!"=="~/JTCS-final" set "VPS_PATH=/root/JTCS-final"
for /f "delims=" %%B in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "LOCAL_BRANCH=%%B"
if "!LOCAL_BRANCH!"=="" set "LOCAL_BRANCH=main"
where ssh >nul 2>&1
if errorlevel 1 (
    echo ERROR: ssh not found. Install OpenSSH Client.
    pause
    goto menu
)
echo Host: !VPS_USER!@!VPS_HOST!  Path: !VPS_PATH!  Branch: !LOCAL_BRANCH!
echo Enter VPS password when asked.
echo.
ssh -p !VPS_PORT! -o StrictHostKeyChecking=accept-new !VPS_USER!@!VPS_HOST! "cd !VPS_PATH!; export BRANCH=!LOCAL_BRANCH!; if [ -f scripts/vps_pull_update.sh ]; then bash scripts/vps_pull_update.sh; else git fetch origin; git reset --hard origin/!LOCAL_BRANCH!; fi"
if errorlevel 1 (
    echo Deploy failed.
    pause
    goto menu
)
echo Deploy OK. http://!VPS_HOST!:8000/login
pause
goto menu

:oneclick
echo.
echo [9] ONE CLICK Push + Deploy...
cd /d "%~dp0"
set "VPS_HOST=200.141.5.68"
set "VPS_USER=root"
set "VPS_PORT=22"
set "VPS_PATH=/root/JTCS-final"
if exist "deploy_vps.env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in (`powershell -NoProfile -Command "Get-Content -LiteralPath 'deploy_vps.env' | ForEach-Object { $_ -replace '`r','' }"`) do (
        if not "%%A"=="" set "%%A=%%B"
    )
)
if /i "!VPS_PATH!"=="~/JTCS-final" set "VPS_PATH=/root/JTCS-final"
where git >nul 2>&1
if errorlevel 1 (
    echo ERROR: git not found.
    pause
    goto menu
)
where ssh >nul 2>&1
if errorlevel 1 (
    echo ERROR: ssh not found.
    pause
    goto menu
)
set "COMMIT_MSG="
set /p COMMIT_MSG="Commit message: "
if "!COMMIT_MSG!"=="" (
    for /f "tokens=1-3 delims=/ " %%a in ("%date%") do set "D=%%a-%%b-%%c"
    for /f "tokens=1-2 delims=:." %%a in ("%time%") do set "T=%%a%%b"
    set "COMMIT_MSG=update !D! !T!"
)
echo.
echo [1/2] GitHub push...
git add -A
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "!COMMIT_MSG!"
    if errorlevel 1 (
        echo Commit failed.
        pause
        goto menu
    )
) else (
    echo Nothing new to commit.
)
git push -u origin HEAD
if errorlevel 1 (
    echo Push failed.
    pause
    goto menu
)
echo Push OK.
for /f "delims=" %%B in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "LOCAL_BRANCH=%%B"
if "!LOCAL_BRANCH!"=="" set "LOCAL_BRANCH=main"
echo.
echo [2/2] VPS deploy !VPS_USER!@!VPS_HOST! ...
echo Enter VPS password when asked.
ssh -p !VPS_PORT! -o StrictHostKeyChecking=accept-new !VPS_USER!@!VPS_HOST! "cd !VPS_PATH!; export BRANCH=!LOCAL_BRANCH!; if [ -f scripts/vps_pull_update.sh ]; then bash scripts/vps_pull_update.sh; else git fetch origin; git reset --hard origin/!LOCAL_BRANCH!; fi"
if errorlevel 1 (
    echo Deploy failed.
    pause
    goto menu
)
echo.
echo DONE. http://!VPS_HOST!:8000/login
pause
goto menu

:dbschema
echo.
echo [D] Schema-only database update (DATA safe)...
cd /d "%~dp0erp"
if not exist ".venv\Scripts\python.exe" (
    echo ERROR: venv missing. Run option 1 first.
    pause
    cd /d "%~dp0"
    goto menu
)
".venv\Scripts\python.exe" scripts\apply_schema_migrations.py
if errorlevel 1 (
    echo Schema update failed. Data was not overwritten.
    pause
    cd /d "%~dp0"
    goto menu
)
echo Done.
pause
cd /d "%~dp0"
goto menu
