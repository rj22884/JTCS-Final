@echo off
title JTCS Fix 502 NOW
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "VPS_HOST=200.234.41.220"
set "VPS_USER=root"
set "VPS_PORT=22"
set "VPS_PATH=/root/JTCS-final"
set "GIT_REPO_URL=https://github.com/rj22884/JTCS-Final.git"
set "PUBLIC_HEALTH_URL=https://app.jtcsxpert.com/health"
set "LOG_DIR=%ROOT%\deployment\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1

for /f "delims=" %%B in ('git -C "%ROOT%" branch --show-current 2^>nul') do set "LOCAL_BRANCH=%%B"
if "!LOCAL_BRANCH!"=="" set "LOCAL_BRANCH=cursor/one-click-deploy-bat-8e65"

echo.
echo ========================================
echo  JTCS - FIX 502 NOW
echo  https://app.jtcsxpert.com
echo ========================================
echo  Branch : !LOCAL_BRANCH!
echo  VPS    : %VPS_USER%@%VPS_HOST%:%VPS_PATH%
echo.

if not exist "%ROOT%\erp\.env" (
  echo [FAIL] Missing erp\.env
  pause
  exit /b 1
)
if not exist "%ROOT%\deployment\vps_repair_502.sh" (
  echo [FAIL] Missing deployment\vps_repair_502.sh
  pause
  exit /b 1
)

set "DEPLOY_LOG=%LOG_DIR%\repair_now_%RANDOM%.log"
set "REMOTE_ENV=/tmp/jtcs.env.from_windows"
set "REMOTE_REPAIR=/tmp/jtcs_repair_502.sh"

echo [1/3] Upload erp\.env ...
echo Enter VPS password when asked.
scp -P %VPS_PORT% -o StrictHostKeyChecking=accept-new "%ROOT%\erp\.env" %VPS_USER%@%VPS_HOST%:%REMOTE_ENV%
if errorlevel 1 (
  echo [FAIL] scp .env failed
  pause
  exit /b 1
)

echo [2/3] Upload repair script ...
scp -P %VPS_PORT% -o StrictHostKeyChecking=accept-new "%ROOT%\deployment\vps_repair_502.sh" %VPS_USER%@%VPS_HOST%:%REMOTE_REPAIR%
if errorlevel 1 (
  echo [FAIL] scp repair script failed
  pause
  exit /b 1
)

echo [3/3] Repair + restart on VPS ...
echo Enter VPS password again.
ssh -p %VPS_PORT% -o StrictHostKeyChecking=accept-new %VPS_USER%@%VPS_HOST% "sed -i 's/\r$//' %REMOTE_REPAIR% && bash %REMOTE_REPAIR% %VPS_PATH% !LOCAL_BRANCH! %GIT_REPO_URL%" > "%DEPLOY_LOG%" 2>&1
set "SSH_RC=!ERRORLEVEL!"
type "%DEPLOY_LOG%"
echo.

findstr /I /C:"DEPLOY_RESULT:SUCCESS" "%DEPLOY_LOG%" >nul 2>&1
if errorlevel 1 (
  if not "!SSH_RC!"=="0" (
    echo [FAIL] Repair failed. Log: %DEPLOY_LOG%
    echo If tree missing, run JTCS_ERP.bat option 3
    pause
    exit /b 1
  )
)

echo Checking https://app.jtcsxpert.com/health ...
powershell -NoProfile -Command "try { $r=Invoke-WebRequest -Uri '%PUBLIC_HEALTH_URL%' -UseBasicParsing -TimeoutSec 30; if($r.StatusCode -eq 200){Write-Host '[PASS] LIVE OK - https://app.jtcsxpert.com'; exit 0} else {Write-Host ('[FAIL] HTTP '+$r.StatusCode); exit 1} } catch { Write-Host ('[FAIL] '+$_.Exception.Message); exit 1 }"
if errorlevel 1 (
  echo [FAIL] Still 502/unhealthy. Log: %DEPLOY_LOG%
  pause
  exit /b 1
)

echo.
echo [PASS] 502 FIXED
start https://app.jtcsxpert.com/login
pause
exit /b 0
