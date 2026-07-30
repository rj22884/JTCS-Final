@echo off
REM =============================================================================
REM JTCS ERP — setup_deployment.bat (Windows workstation bootstrap)
REM =============================================================================
setlocal EnableExtensions
cd /d "%~dp0\.."
set "REPO_ROOT=%CD%"
set "DEPLOY_DIR=%REPO_ROOT%\deployment"

echo ========================================
echo  JTCS ERP — Deployment Setup (Windows)
echo ========================================
echo.

where git >nul 2>&1 || (echo Install Git for Windows first. & pause & exit /b 1)
where ssh >nul 2>&1 || (echo Enable OpenSSH Client first. & pause & exit /b 1)

if not exist "%DEPLOY_DIR%\deploy.env" (
  copy /Y "%DEPLOY_DIR%\config\deploy.env.example" "%DEPLOY_DIR%\deploy.env" >nul
  echo Created deployment\deploy.env — EDIT this file now.
) else (
  echo deploy.env already exists.
)

echo.
echo Next steps:
echo  1. Edit deployment\deploy.env  (VPS_SSH_HOST, VPS_APP_DIR, HEALTH_URL)
echo  2. Generate SSH key if needed:
echo       ssh-keygen -t ed25519 -f %%USERPROFILE%%\.ssh\jtcs_deploy_ed25519 -C "jtcs-deploy"
echo  3. Copy public key to VPS:
echo       type %%USERPROFILE%%\.ssh\jtcs_deploy_ed25519.pub ^| ssh USER@HOST "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
echo  4. Set VPS_SSH_KEY in deploy.env to that private key path
echo  5. On VPS run:  bash deployment/setup_deployment.sh
echo  6. Double-click deployment\deploy.bat to deploy
echo.
pause
endlocal
