@echo off
title JTCS ERP - Schema Update (DATA SAFE)
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo ========================================================
echo   JTCS ERP - Database SCHEMA update only
echo ========================================================
echo   Existing data is NEVER deleted or overwritten.
echo   Only missing tables / columns / indexes are applied.
echo ========================================================
echo.

cd /d "%~dp0erp"
if errorlevel 1 (
    echo [ERROR] erp folder nahi mili.
    pause
    exit /b 1
)

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" scripts\apply_schema_migrations.py
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python / venv nahi mila. Pehle install_jtcs_erp.bat chalao.
        pause
        exit /b 1
    )
    python scripts\apply_schema_migrations.py
)

set "EXITCODE=%ERRORLEVEL%"
echo.
if not "%EXITCODE%"=="0" (
    echo [ERROR] Schema update fail. Data touch nahi hua.
    pause
    exit /b %EXITCODE%
)

echo Done. App restart karo agar chal rahi ho: stop + start.
pause
endlocal
exit /b 0
