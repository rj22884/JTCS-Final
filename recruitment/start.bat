@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

set "PY=%~dp0.venv\Scripts\python.exe"
set "HOST=127.0.0.1"
set "PORT=5050"
set "SESSION_COOKIE_SECURE=false"
set "PREFERRED_URL_SCHEME=http"
set "PYTHONUNBUFFERED=1"

if not exist "%PY%" (
  echo Creating virtual environment...
  python -m venv "%~dp0.venv"
  if errorlevel 1 (
    echo ERROR: Python venv could not be created. Install Python 3 and try again.
    pause
    exit /b 1
  )
)

echo Installing requirements...
"%PY%" -m pip install -q -r "%~dp0requirements.txt"
if errorlevel 1 (
  echo ERROR: pip install failed.
  pause
  exit /b 1
)

if not exist "%~dp0.env" copy "%~dp0.env.example" "%~dp0.env" >nul

echo Preparing database...
"%PY%" -m flask --app recruitment init-db
if errorlevel 1 (
  echo WARNING: init-db reported an error. Continuing with existing database.
)

echo Freeing port %PORT% if an old server is still running...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%PORT%" ^| findstr "LISTENING"') do (
  taskkill /F /PID %%P >nul 2>&1
)

echo.
echo Recruitment is a standalone app (not the website, not ERP).
echo Apply form:          http://127.0.0.1:%PORT%/careers/apply/sales-executive
echo Application status:  http://127.0.0.1:%PORT%/careers/application-status
echo Admin login:         http://127.0.0.1:%PORT%/recruitment/admin/login
echo Website (optional):  http://localhost:5500
echo ERP (optional):      http://localhost:8000
echo.

"%PY%" -m recruitment
set "ERR=%ERRORLEVEL%"
if not "%ERR%"=="0" (
  echo.
  echo ERROR: Recruitment server stopped. Port %PORT% may be in use, or Python failed to start.
  echo Close any other window that is already using http://127.0.0.1:%PORT% and run start.bat again.
  pause
  exit /b %ERR%
)
endlocal
