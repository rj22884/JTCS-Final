@echo off
title JTCS ERP - Launcher
setlocal EnableExtensions

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
echo    0. Exit
echo.
set /p choice="Select option (0-9): "

if "%choice%"=="1" goto install
if "%choice%"=="2" goto start
if "%choice%"=="3" goto stop
if "%choice%"=="4" goto test
if "%choice%"=="5" goto browser
if "%choice%"=="6" goto editenv
if "%choice%"=="7" goto pushgit
if "%choice%"=="8" goto deployvps
if "%choice%"=="9" goto oneclick
if "%choice%"=="0" exit /b 0
goto menu

:install
call "%~dp0install_jtcs_erp.bat"
goto menu

:start
call "%~dp0start_jtcs_erp.bat"
goto menu

:stop
call "%~dp0stop_jtcs_erp.bat"
goto menu

:test
cd /d "%~dp0erp"
call ".venv\Scripts\activate.bat"
python scripts\test_auth.py
echo.
pause
goto menu

:browser
start "" "http://localhost:8000/login"
goto menu

:editenv
notepad "%~dp0erp\.env"
goto menu

:pushgit
call "%~dp0push_to_git.bat"
goto menu

:deployvps
call "%~dp0deploy_to_vps.bat"
goto menu

:oneclick
call "%~dp0PUSH_AND_DEPLOY.bat"
goto menu
