@echo off
title JTCS ERP - Stop Server
setlocal EnableDelayedExpansion

set PORT=8000
if not "%~1"=="" set PORT=%~1

echo Stopping JTCS ERP on port %PORT%...

for /f "tokens=2" %%p in ('wmic process where "CommandLine like '%%uvicorn%%'" get ProcessId /value 2^>nul ^| findstr "ProcessId"') do (
    set PID=%%p
    set PID=!PID:ProcessId=!
    if defined PID (
        echo Stopping uvicorn PID !PID!
        taskkill /PID !PID! /F >nul 2>&1
    )
)

for /f "tokens=2" %%p in ('wmic process where "CommandLine like '%%JTCS Final\\backend%%'" get ProcessId /value 2^>nul ^| findstr "ProcessId"') do (
    set PID=%%p
    set PID=!PID:ProcessId=!
    if defined PID (
        echo Stopping backend PID !PID!
        taskkill /PID !PID! /F >nul 2>&1
    )
)

for /f "tokens=2" %%p in ('wmic process where "CommandLine like '%%JTCS Final\\erp%%run.py%%'" get ProcessId /value 2^>nul ^| findstr "ProcessId"') do (
    set PID=%%p
    set PID=!PID:ProcessId=!
    if defined PID (
        echo Stopping JTCS ERP PID !PID!
        taskkill /PID !PID! /F >nul 2>&1
    )
)

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    echo Stopping port %PORT% listener PID %%a
    taskkill /PID %%a /F >nul 2>&1
)

timeout /t 2 >nul
echo Done.
endlocal
