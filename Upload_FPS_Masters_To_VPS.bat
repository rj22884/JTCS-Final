@echo off
REM =============================================================================
REM Upload DistrictWiseFpsDetails_Merged_WithCodes.xlsx to LIVE VPS masters
REM STRICT: only https://app.jtcsxpert.com/public-report/ration-card
REM   (State / District / DSO / ARO / FPS master tables)
REM Does NOT deploy code. Does NOT touch other ERP modules.
REM =============================================================================
title JTCS Upload FPS Masters to VPS
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"

set "SOURCE_XLSX=C:\Users\USER\Downloads\DistrictWiseFpsDetails_Merged_WithCodes.xlsx"
set "LOCAL_TEMP=C:\temp"
set "LOCAL_STAGING=%LOCAL_TEMP%\jtcs_fps_upload"
set "LOCAL_XLSX=%LOCAL_STAGING%\DistrictWiseFpsDetails_Merged_WithCodes.xlsx"
set "LOCAL_SH=%LOCAL_STAGING%\vps_import_fps_masters_only.sh"
set "LOCAL_PY=%ROOT%\erp\scripts\import_fps_masters_excel.py"
set "LOCAL_REMOTE_SH=%ROOT%\deployment\vps_import_fps_masters_only.sh"

set "VPS_HOST=200.234.41.220"
set "VPS_USER=root"
set "VPS_PORT=22"
set "VPS_PATH=/root/JTCS-final"
set "REMOTE_STAGING=/tmp/jtcs_fps_import"
set "REMOTE_XLSX=%REMOTE_STAGING%/DistrictWiseFpsDetails_Merged_WithCodes.xlsx"
set "REMOTE_SH=%REMOTE_STAGING%/vps_import_fps_masters_only.sh"
set "PUBLIC_URL=https://app.jtcsxpert.com/public-report/ration-card"

echo.
echo ========================================
echo  JTCS — Upload FPS Excel to VPS masters
echo  STRICT overwrite only:
echo    %PUBLIC_URL%
echo  Tables: State / District / DSO / ARO / FPS
echo ========================================
echo  Excel : %SOURCE_XLSX%
echo  VPS   : %VPS_USER%@%VPS_HOST%:%VPS_PATH%
echo.

if not exist "%SOURCE_XLSX%" (
  echo [FAIL] Excel missing:
  echo        %SOURCE_XLSX%
  pause
  exit /b 1
)
if not exist "%LOCAL_PY%" (
  echo [FAIL] Import script missing:
  echo        %LOCAL_PY%
  pause
  exit /b 1
)
if not exist "%LOCAL_REMOTE_SH%" (
  echo [FAIL] Remote runner missing:
  echo        %LOCAL_REMOTE_SH%
  pause
  exit /b 1
)

where scp >nul 2>&1
if errorlevel 1 (
  echo [FAIL] OpenSSH scp not found. Enable OpenSSH Client.
  pause
  exit /b 1
)
where ssh >nul 2>&1
if errorlevel 1 (
  echo [FAIL] OpenSSH ssh not found. Enable OpenSSH Client.
  pause
  exit /b 1
)

echo [1/5] Clear previous C:\temp staging for this job ...
if not exist "%LOCAL_TEMP%" mkdir "%LOCAL_TEMP%" >nul 2>&1
if exist "%LOCAL_STAGING%" (
  echo       Removing %LOCAL_STAGING%
  rd /s /q "%LOCAL_STAGING%"
)
REM leftover copies from older runs (this job only — not whole C:\temp)
del /q "%LOCAL_TEMP%\DistrictWiseFpsDetails_Merged_WithCodes.xlsx" >nul 2>&1
del /q "%LOCAL_TEMP%\DistrictWiseFps*.xlsx" >nul 2>&1
del /q "%LOCAL_TEMP%\import_fps_masters_excel.py" >nul 2>&1
del /q "%LOCAL_TEMP%\vps_import_fps_masters_only.sh" >nul 2>&1
del /q "%LOCAL_TEMP%\jtcs_fps*.*" >nul 2>&1
mkdir "%LOCAL_STAGING%" >nul 2>&1
echo       OK

echo [2/5] Stage Excel + runner under C:\temp ...
copy /Y "%SOURCE_XLSX%" "%LOCAL_XLSX%" >nul
if errorlevel 1 (
  echo [FAIL] Could not copy Excel to %LOCAL_XLSX%
  pause
  exit /b 1
)
copy /Y "%LOCAL_REMOTE_SH%" "%LOCAL_SH%" >nul
if errorlevel 1 (
  echo [FAIL] Could not copy runner to %LOCAL_SH%
  pause
  exit /b 1
)
REM Force Unix (LF) line endings so VPS bash does not fail on pipefail/CRLF
python -c "from pathlib import Path; p=Path(r'%LOCAL_SH%'); p.write_bytes(p.read_bytes().replace(b'\r\n',b'\n').replace(b'\r',b'\n'))"
if errorlevel 1 (
  echo [FAIL] Could not convert runner to LF line endings
  pause
  exit /b 1
)
echo       OK - %LOCAL_XLSX%

echo [3/5] Upload to VPS staging %REMOTE_STAGING% ...
echo       Enter VPS password when asked.
ssh -p %VPS_PORT% -o StrictHostKeyChecking=accept-new %VPS_USER%@%VPS_HOST% "rm -rf '%REMOTE_STAGING%' && mkdir -p '%REMOTE_STAGING%'"
if errorlevel 1 (
  echo [FAIL] Could not prepare remote staging
  pause
  exit /b 1
)
scp -P %VPS_PORT% -o StrictHostKeyChecking=accept-new "%LOCAL_XLSX%" %VPS_USER%@%VPS_HOST%:%REMOTE_XLSX%
if errorlevel 1 (
  echo [FAIL] scp Excel failed
  pause
  exit /b 1
)
scp -P %VPS_PORT% -o StrictHostKeyChecking=accept-new "%LOCAL_SH%" %VPS_USER%@%VPS_HOST%:%REMOTE_SH%
if errorlevel 1 (
  echo [FAIL] scp runner failed
  pause
  exit /b 1
)
REM Also refresh import script on VPS so live uses current code for THIS import only
scp -P %VPS_PORT% -o StrictHostKeyChecking=accept-new "%LOCAL_PY%" %VPS_USER%@%VPS_HOST%:%VPS_PATH%/erp/scripts/import_fps_masters_excel.py
if errorlevel 1 (
  echo [FAIL] scp import_fps_masters_excel.py failed
  pause
  exit /b 1
)
echo       OK

echo [4/5] Run STRICT import on VPS live DB ...
echo       Scope locked to public-report/ration-card masters ONLY.
ssh -p %VPS_PORT% -o StrictHostKeyChecking=accept-new %VPS_USER%@%VPS_HOST% "sed -i 's/\r$//' '%REMOTE_SH%' '%VPS_PATH%/erp/scripts/import_fps_masters_excel.py' 2>/dev/null; chmod +x '%REMOTE_SH%'; VPS_APP_DIR='%VPS_PATH%' bash '%REMOTE_SH%' '%REMOTE_XLSX%'"
if errorlevel 1 (
  echo [FAIL] Remote import failed
  pause
  exit /b 1
)
echo       OK

echo [5/5] Clear local C:\temp staging again ...
if exist "%LOCAL_STAGING%" rd /s /q "%LOCAL_STAGING%"
del /q "%LOCAL_TEMP%\DistrictWiseFpsDetails_Merged_WithCodes.xlsx" >nul 2>&1
echo       OK

echo.
echo ========================================
echo  DONE — masters overwritten on live VPS
echo  Open: %PUBLIC_URL%/fps-master
echo  Open: %PUBLIC_URL%/district-master
echo ========================================
echo.
start "" "%PUBLIC_URL%/fps-master"
pause
exit /b 0
