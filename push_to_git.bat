@echo off
title JTCS ERP - Push to GitHub
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"
if errorlevel 1 (
    echo ERROR: Could not open project folder.
    pause
    exit /b 1
)

where git >nul 2>&1
if errorlevel 1 (
    echo ERROR: git not found. Install Git for Windows first.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   JTCS ERP - Push code to GitHub
echo ========================================
echo   Folder : %CD%
echo.

git status -sb
echo.

set "MSG="
set /p MSG="Commit message (Enter = auto timestamp): "
if "%MSG%"=="" (
    for /f "tokens=1-3 delims=/ " %%a in ("%date%") do set "D=%%a-%%b-%%c"
    for /f "tokens=1-2 delims=:." %%a in ("%time%") do set "T=%%a%%b"
    set "MSG=update %D% %T%"
)

echo.
echo Staging changes (erp\.env is ignored — secrets stay local)...
git add -A
git status -sb
echo.

git diff --cached --quiet
if not errorlevel 1 (
    echo Nothing new to commit.
    echo Checking remote push...
    git push
    if errorlevel 1 (
        echo.
        echo Push failed. Check internet / GitHub login.
        pause
        exit /b 1
    )
    echo.
    echo Already up to date on GitHub.
    pause
    exit /b 0
)

git commit -m "%MSG%"
if errorlevel 1 (
    echo.
    echo Commit failed.
    pause
    exit /b 1
)

echo.
echo Pushing to GitHub...
git push -u origin HEAD
if errorlevel 1 (
    echo.
    echo Push failed. Try: git push -u origin main
    pause
    exit /b 1
)

echo.
echo ========================================
echo   DONE - code is on GitHub
echo ========================================
echo   Next: run deploy_to_vps.bat
echo   Or on VPS:
echo     cd ~/JTCS-final
echo     bash scripts/vps_pull_update.sh
echo ========================================
echo.
pause
endlocal
