@echo off
setlocal EnableExtensions DisableDelayedExpansion
title JTCS StampMaster NULL Update on VPS

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
if not exist "%ROOT%\deployment\update_stampmaster_nulls.py" set "ROOT=E:\Git\JTCS Final"
set "VPS_HOST=200.234.41.220"
set "VPS_USER=root"
set "VPS_PORT=22"
set "VPS_APP_DIR=/root/JTCS-final"
set "LOCAL_STAGING=C:\temp\jtcs_stampmaster_update"
set "LOCAL_PY=%ROOT%\deployment\update_stampmaster_nulls.py"
set "LOCAL_SH=%ROOT%\deployment\run_stampmaster_null_update.sh"
set "REMOTE_STAGING=/tmp/jtcs_stampmaster_update"

:menu
cls
echo ==========================================
echo JTCS StampMaster NULL field update
echo VPS: %VPS_HOST%
echo App: %VPS_APP_DIR%
echo ==========================================
echo 1. Update MobileNumber NULL to 9837012345
echo 2. Update EntrySource NULL to manual
echo 3. Exit
set "OPTION="
set /p "OPTION=Choose 1, 2, or 3: "

if "%OPTION%"=="3" goto exit
if not "%OPTION%"=="1" if not "%OPTION%"=="2" (
  echo Invalid choice.
  pause
  goto menu
)

if not exist "%LOCAL_PY%" (
  echo [FAIL] Update runner missing: %LOCAL_PY%
  pause
  goto menu
)
if not exist "%LOCAL_SH%" (
  echo [FAIL] VPS runner missing: %LOCAL_SH%
  pause
  goto menu
)
where ssh >nul 2>&1
if errorlevel 1 (
  echo [FAIL] OpenSSH ssh not found. Enable the Windows OpenSSH Client.
  pause
  goto menu
)
where scp >nul 2>&1
if errorlevel 1 (
  echo [FAIL] OpenSSH scp not found. Enable the Windows OpenSSH Client.
  pause
  goto menu
)

if not exist "%LOCAL_STAGING%" mkdir "%LOCAL_STAGING%" >nul 2>&1
copy /Y "%LOCAL_PY%" "%LOCAL_STAGING%\update_stampmaster_nulls.py" >nul
if errorlevel 1 (
  echo [FAIL] Could not stage the Python runner.
  pause
  goto menu
)
copy /Y "%LOCAL_SH%" "%LOCAL_STAGING%\run_stampmaster_null_update.sh" >nul
if errorlevel 1 (
  echo [FAIL] Could not stage the VPS runner.
  pause
  goto menu
)
python -c "from pathlib import Path; p=Path(r'%LOCAL_STAGING%\run_stampmaster_null_update.sh'); p.write_bytes(p.read_bytes().replace(b'\r\n',b'\n').replace(b'\r',b'\n'))"
if errorlevel 1 (
  echo [FAIL] Could not convert the VPS runner to Unix line endings.
  pause
  goto menu
)

echo.
echo Uploading the update runner to the VPS.
echo Enter the VPS SSH password when prompted.
ssh -p %VPS_PORT% -o StrictHostKeyChecking=accept-new %VPS_USER%@%VPS_HOST% "mkdir -p '%REMOTE_STAGING%'"
if errorlevel 1 (
  echo [FAIL] Could not prepare remote staging.
  pause
  goto menu
)
scp -P %VPS_PORT% -o StrictHostKeyChecking=accept-new "%LOCAL_STAGING%\update_stampmaster_nulls.py" %VPS_USER%@%VPS_HOST%:%REMOTE_STAGING%/update_stampmaster_nulls.py
if errorlevel 1 (
  echo [FAIL] Could not upload the Python runner.
  pause
  goto menu
)
scp -P %VPS_PORT% -o StrictHostKeyChecking=accept-new "%LOCAL_STAGING%\run_stampmaster_null_update.sh" %VPS_USER%@%VPS_HOST%:%REMOTE_STAGING%/run_stampmaster_null_update.sh
if errorlevel 1 (
  echo [FAIL] Could not upload the VPS runner.
  pause
  goto menu
)

echo.
echo The live application database settings will be used.
echo Rows will be previewed; the database updates only after typing YES.
ssh -tt -p %VPS_PORT% -o StrictHostKeyChecking=accept-new %VPS_USER%@%VPS_HOST% "chmod 700 '%REMOTE_STAGING%/run_stampmaster_null_update.sh'; VPS_APP_DIR='%VPS_APP_DIR%' bash '%REMOTE_STAGING%/run_stampmaster_null_update.sh' %OPTION%"
if errorlevel 1 (
  echo [FAIL] Remote preview/update returned an error.
)

echo.
pause
goto menu

:exit
endlocal
exit /b 0
