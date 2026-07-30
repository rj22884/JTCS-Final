@echo off
REM =============================================================================
REM JTCS ERP — deploy.bat (Windows one-click deploy)
REM Double-click this file from Explorer after coding in Cursor / VS Code.
REM Flow: git status → add → commit → tag → push → SSH deploy on Ubuntu VPS
REM =============================================================================
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0\.."
set "REPO_ROOT=%CD%"
set "DEPLOY_DIR=%REPO_ROOT%\deployment"
set "ENV_FILE=%DEPLOY_DIR%\deploy.env"

echo.
echo ========================================
echo   JTCS ERP — One-Click Deployment
echo ========================================
echo Repo: %REPO_ROOT%
echo.

if not exist "%ENV_FILE%" (
  if exist "%DEPLOY_DIR%\config\deploy.env.example" (
    echo [WARN] deploy.env missing. Copying example — EDIT IT before production use.
    copy /Y "%DEPLOY_DIR%\config\deploy.env.example" "%ENV_FILE%" >nul
  ) else (
    echo [ERROR] Missing %ENV_FILE%
    pause
    exit /b 1
  )
)

REM Load KEY=VALUE pairs from deploy.env (skip comments / blanks)
for /f "usebackq tokens=1,* delims== eol=#" %%A in ("%ENV_FILE%") do (
  if not "%%A"=="" (
    set "%%A=%%B"
  )
)

where git >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Git is not installed or not on PATH.
  pause
  exit /b 1
)

where ssh >nul 2>&1
if errorlevel 1 (
  echo [ERROR] OpenSSH client ^(ssh^) not found. Enable OpenSSH Client in Windows Optional Features.
  pause
  exit /b 1
)

echo [1/10] Git status
git status -sb
echo.

set "COMMIT_MSG="
set /p COMMIT_MSG=Commit message (Enter for 'Auto Deployment'): 
if "!COMMIT_MSG!"=="" set "COMMIT_MSG=Auto Deployment"

set "VERSION="
set /p VERSION=Version number e.g. 1.0.1 (Enter to auto on server): 

set "RELEASE_NOTES="
set /p RELEASE_NOTES=Release notes: 

set "DEVELOPER="
set /p DEVELOPER=Developer name: 
if "!DEVELOPER!"=="" if defined DEFAULT_DEVELOPER set "DEVELOPER=!DEFAULT_DEVELOPER!"

set "WHATS_NEW="
set /p WHATS_NEW=What's New (optional): 
set "BUG_FIXES="
set /p BUG_FIXES=Bug Fixes (optional): 
set "FEATURES="
set /p FEATURES=New Features (optional): 

set "BRANCH=main"
if defined GIT_BRANCH set "BRANCH=!GIT_BRANCH!"
set "REMOTE=origin"
if defined GIT_REMOTE set "REMOTE=!GIT_REMOTE!"

echo.
echo [2/10] Staging all changes
git add -A
git status -sb

echo.
echo [3/10] Commit
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "!COMMIT_MSG!"
  if errorlevel 1 (
    echo [ERROR] Git commit failed — deployment stopped.
    pause
    exit /b 1
  )
) else (
  echo No staged changes to commit — continuing with existing HEAD.
)

if not "!VERSION!"=="" (
  echo [4/10] Creating git tag v!VERSION!
  git tag -a "v!VERSION!" -m "Release v!VERSION! — !COMMIT_MSG!" 2>nul
  if errorlevel 1 (
    echo [WARN] Tag v!VERSION! may already exist — continuing.
  )
) else (
  echo [4/10] Skipping git tag ^(no version entered^)
)

echo.
echo [5/10] Push branch !BRANCH! to !REMOTE!
git push -u !REMOTE! HEAD:!BRANCH!
if errorlevel 1 (
  echo [ERROR] Git push failed — deployment stopped.
  pause
  exit /b 1
)

if not "!VERSION!"=="" (
  echo [6/10] Push tag v!VERSION!
  git push !REMOTE! "v!VERSION!"
  if errorlevel 1 (
    echo [WARN] Tag push failed — continuing with remote deploy.
  )
) else (
  echo [6/10] No tag to push
)

if not defined VPS_SSH_HOST (
  echo [ERROR] VPS_SSH_HOST not set in deploy.env
  pause
  exit /b 1
)

set "SSH_OPTS=-o BatchMode=yes -o StrictHostKeyChecking=accept-new"
if defined VPS_SSH_PORT set "SSH_OPTS=!SSH_OPTS! -p !VPS_SSH_PORT!"
if defined VPS_SSH_KEY if not "!VPS_SSH_KEY!"=="" set "SSH_OPTS=!SSH_OPTS! -i "!VPS_SSH_KEY!""

set "REMOTE_SCRIPT=!VPS_APP_DIR!/deployment/deploy.sh"
if "!VPS_APP_DIR!"=="" set "REMOTE_SCRIPT=/var/www/jtcs-erp/deployment/deploy.sh"

echo.
echo [7/10] SSH to !VPS_SSH_HOST!
echo [8/10] Running remote deploy.sh
echo.

REM Escape quotes for remote bash by using single-quoted args carefully
set "REMOTE_CMD=bash "!REMOTE_SCRIPT!""
if not "!VERSION!"=="" set "REMOTE_CMD=!REMOTE_CMD! --version '!VERSION!'"
if not "!RELEASE_NOTES!"=="" set "REMOTE_CMD=!REMOTE_CMD! --notes '!RELEASE_NOTES!'"
if not "!DEVELOPER!"=="" set "REMOTE_CMD=!REMOTE_CMD! --developer '!DEVELOPER!'"
if not "!WHATS_NEW!"=="" set "REMOTE_CMD=!REMOTE_CMD! --whats-new '!WHATS_NEW!'"
if not "!BUG_FIXES!"=="" set "REMOTE_CMD=!REMOTE_CMD! --bug-fixes '!BUG_FIXES!'"
if not "!FEATURES!"=="" set "REMOTE_CMD=!REMOTE_CMD! --features '!FEATURES!'"

ssh !SSH_OPTS! !VPS_SSH_HOST! "!REMOTE_CMD!"
set "DEPLOY_EXIT=!ERRORLEVEL!"

echo.
if not "!DEPLOY_EXIT!"=="0" (
  echo [9/10] Deployment FAILED ^(exit !DEPLOY_EXIT!^)
  echo Check VPS logs under /var/log/jtcs-erp/
  echo.
  pause
  exit /b !DEPLOY_EXIT!
)

echo [9/10] Deployment succeeded
echo [10/10] Done.
echo.
pause
endlocal
exit /b 0
