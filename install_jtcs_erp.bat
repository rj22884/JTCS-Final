@echo off
title JTCS ERP - Install
setlocal

set "ROOT=%~dp0"
set "ERP=%ROOT%erp"

cd /d "%ERP%"
if errorlevel 1 (
    echo ERROR: Could not open folder: %ERP%
    pause
    exit /b 1
)

echo.
echo ========================================
echo   JTCS ERP - First-time setup
echo ========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.11+ and try again.
    pause
    exit /b 1
)

python --version

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"

echo Installing dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed.
    pause
    exit /b 1
)

if not exist ".env" (
    if exist ".env.example" (
        copy /Y ".env.example" ".env" >nul
        echo Created .env from .env.example
        echo Edit .env and set MAIL_PASSWORD before using email features.
    ) else (
        echo WARNING: .env.example not found.
    )
) else (
    echo .env already exists - not overwritten.
)

echo.
echo Applying database SCHEMA updates (data safe)...
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" scripts\apply_schema_migrations.py
    if errorlevel 1 (
        echo WARNING: Schema update failed. Run update_database.bat manually.
    ) else (
        echo Database schema update applied. Existing data preserved.
    )
) else (
    echo WARNING: venv python not found. Run update_database.bat manually.
)

echo.
echo ========================================
echo   Setup complete
echo ========================================
echo   Next steps:
echo   1. Edit %ERP%\.env
echo   2. Set MAIL_PASSWORD for Gmail SMTP
echo   3. Run start_jtcs_erp.bat
echo ========================================
echo.
pause
endlocal
