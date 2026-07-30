@echo off
REM Convenience launcher — one-click from repo root
cd /d "%~dp0"
call "%~dp0deployment\deploy.bat"
