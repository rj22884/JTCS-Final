@echo off
REM Launcher for Windows Task Scheduler / background start (handles spaces in path)
cd /d "%~dp0.."
start "JTCS Auto Backup" /MIN powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0local_auto_backup.ps1" -Watch -Source "%cd%" -BackupRoot "D:\JTCS Backup"
exit /b 0
