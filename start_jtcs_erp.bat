@echo off
title JTCS ERP
setlocal EnableDelayedExpansion

set "ROOT=%~dp0"
set "ERP=%ROOT%erp"

cd /d "%ERP%"
if errorlevel 1 (
    echo ERROR: Could not open folder: %ERP%
    pause
    exit /b 1
)

if not exist ".venv\Scripts\activate.bat" (
    echo Virtual environment not found.
    echo Run first: install_jtcs_erp.bat
    pause
    exit /b 1
)

echo Stopping any old server on port 8000...
call "%ROOT%stop_jtcs_erp.bat"

call ".venv\Scripts\activate.bat"

set PORT=8000

if not exist ".env" (
    echo WARNING: .env file not found.
    echo Run install_jtcs_erp.bat or copy .env.example to .env
    echo.
)

netstat -ano | findstr ":%PORT% " | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo WARNING: Port 8000 may already be in use.
    echo Run stop_jtcs_erp.bat first if the server is stuck.
    echo.
)

echo.
echo ========================================
echo   JTCS ERP - Joshi Tax Consultancy
echo ========================================
echo   Folder : %ERP%
echo   URL    : http://localhost:8000
echo   Login  : http://localhost:8000/login
echo   Auth    : Production auth (link reset, CSRF)
echo ========================================
echo.
echo Press Ctrl+C to stop the server.
echo.

REM Open browser shortly after the waiting page can bind (avoids Chrome "can't be reached").
start "" cmd /c "timeout /t 1 /nobreak >nul & start http://localhost:8000/login"
python run.py

if errorlevel 1 (
    echo.
    echo Server stopped with an error.
    pause
)

endlocal
