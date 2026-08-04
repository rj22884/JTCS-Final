@echo off
title JTCS Local Auto Backup
cd /d "%~dp0"

echo.
echo  JTCS Local Auto Backup
echo  Target: D:\JTCS Backup\Auto
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\local_auto_backup.ps1" -InstallStartup
if errorlevel 1 (
    echo [FAIL] Could not start auto-backup.
    pause
    exit /b 1
)

echo.
echo  Done. Backups appear under:
echo    D:\JTCS Backup\Auto
echo  Log:
echo    D:\JTCS Backup\auto_backup.log
echo.
pause
