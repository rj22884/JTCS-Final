@echo off
title JTCS Launcher
setlocal EnableExtensions EnableDelayedExpansion

set "WEB_PATH=D:\JTCS Web Page"
set "APP_PATH=E:\Git\JTCS Final"
set "WEB_LOCAL=http://localhost:5500"
set "WEB_LIVE=https://jtcsxpert.com"
set "APP_LOCAL=http://localhost:8000"
set "APP_LIVE=https://app.jtcsxpert.com"

:menu
cls
echo.
echo  ========================================
echo   JTCS Launcher  (C:\j.bat)
echo  ========================================
echo.
echo   1. jtcsxpert.com on local
echo   2. jtcsxpert.com on web
echo   3. app.jtcsxpert.com on local
echo   4. app.jtcsxpert.com on web
echo   5. Deploy jtcsxpert.com
echo   6. Deploy app.jtcsxpert.com
echo   7.
echo.
echo  50. Deploy all
echo  51. Exit
echo.
set "choice="
set /p choice="Select option: "
if defined choice set "choice=!choice: =!"

if "!choice!"=="1" goto web_local
if "!choice!"=="2" goto web_live
if "!choice!"=="3" goto app_local
if "!choice!"=="4" goto app_live
if "!choice!"=="5" goto web_deploy
if "!choice!"=="6" goto app_deploy
if "!choice!"=="7" goto blank
if "!choice!"=="50" goto deploy_all
if "!choice!"=="51" exit /b 0

echo.
echo [FAIL] Invalid option: "!choice!"
pause
goto menu

:web_local
echo.
echo [1] jtcsxpert.com on local
echo     Path: %WEB_PATH%
echo     URL : %WEB_LOCAL%
if not exist "%WEB_PATH%\deploy.bat" (
  echo [FAIL] Missing %WEB_PATH%\deploy.bat
  pause
  goto menu
)
start "JTCS Website Local" cmd /k "cd /d \"%WEB_PATH%\" && deploy.bat 1"
timeout /t 2 /nobreak >nul
start "" "%WEB_LOCAL%"
echo [OK] Local website starting. Browser opening %WEB_LOCAL%
pause
goto menu

:web_live
echo.
echo [2] Opening %WEB_LIVE%
start "" "%WEB_LIVE%"
goto menu

:app_local
echo.
echo [3] app.jtcsxpert.com on local
echo     Path: %APP_PATH%
echo     URL : %APP_LOCAL%
if not exist "%APP_PATH%\JTCS_ERP.bat" (
  echo [FAIL] Missing %APP_PATH%\JTCS_ERP.bat
  pause
  goto menu
)
start "JTCS ERP Local" cmd /k "cd /d \"%APP_PATH%\" && JTCS_ERP.bat 1"
timeout /t 2 /nobreak >nul
start "" "%APP_LOCAL%"
echo [OK] Local ERP starting. Browser opening %APP_LOCAL%
pause
goto menu

:app_live
echo.
echo [4] Opening %APP_LIVE%
start "" "%APP_LIVE%"
goto menu

:web_deploy
echo.
echo [5] Deploy jtcsxpert.com
echo     Path: %WEB_PATH%
if not exist "%WEB_PATH%\deploy.bat" (
  echo [FAIL] Missing %WEB_PATH%\deploy.bat
  pause
  goto menu
)
cd /d "%WEB_PATH%"
call deploy.bat 2
echo.
pause
goto menu

:app_deploy
echo.
echo [6] Deploy app.jtcsxpert.com
echo     Path: %APP_PATH%
if not exist "%APP_PATH%\JTCS_ERP.bat" (
  echo [FAIL] Missing %APP_PATH%\JTCS_ERP.bat
  pause
  goto menu
)
cd /d "%APP_PATH%"
call JTCS_ERP.bat 2
echo.
pause
goto menu

:blank
echo.
echo [7] (blank - reserved)
pause
goto menu

:deploy_all
echo.
echo [50] Deploy ALL
echo.
echo --- (A) Website: jtcsxpert.com ---
if not exist "%WEB_PATH%\deploy.bat" (
  echo [FAIL] Missing website deploy.bat
) else (
  cd /d "%WEB_PATH%"
  call deploy.bat 2
)
echo.
echo --- (B) App: app.jtcsxpert.com ---
if not exist "%APP_PATH%\JTCS_ERP.bat" (
  echo [FAIL] Missing JTCS_ERP.bat
) else (
  cd /d "%APP_PATH%"
  call JTCS_ERP.bat 2
)
echo.
echo [DONE] Deploy all finished.
pause
goto menu
