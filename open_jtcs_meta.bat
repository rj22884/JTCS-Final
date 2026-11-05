@echo off
chcp 65001 >nul
title JTCS - Meta Business pages
color 0A

:menu
cls
echo.
echo  ============================================
echo   JTCS - Meta Business pages kholo
echo   Login details nahi maange jaate.
echo   Pehle browser me Meta me logged in raho.
echo  ============================================
echo.
echo   1. Portfolio list          (select)
echo   2. Business Settings       (Accounts / Pages)
echo   3. Business Suite Home
echo   4. WhatsApp Manager
echo   5. Meta Developer Apps
echo   6. Ads Manager
echo   7. Sab important pages ek saath
echo   0. Exit
echo.
set /p choice=Choice (0-7): 

if "%choice%"=="1" goto select
if "%choice%"=="2" goto settings
if "%choice%"=="3" goto home
if "%choice%"=="4" goto whatsapp
if "%choice%"=="5" goto apps
if "%choice%"=="6" goto ads
if "%choice%"=="7" goto all
if "%choice%"=="0" exit /b 0
goto menu

:select
start "" "https://business.facebook.com/select"
echo Portfolio list khuli. Create mat dabao - existing portfolio kholo.
pause
goto menu

:settings
start "" "https://business.facebook.com/settings"
echo Business Settings khuli. Left menu: Accounts - Pages / Instagram / WhatsApp / Apps / Ad accounts
pause
goto menu

:home
start "" "https://business.facebook.com"
pause
goto menu

:whatsapp
start "" "https://business.facebook.com/latest/whatsapp_manager"
pause
goto menu

:apps
start "" "https://developers.facebook.com/apps"
pause
goto menu

:ads
start "" "https://adsmanager.facebook.com"
pause
goto menu

:all
start "" "https://business.facebook.com/select"
timeout /t 1 /nobreak >nul
start "" "https://business.facebook.com/settings"
timeout /t 1 /nobreak >nul
start "" "https://business.facebook.com"
timeout /t 1 /nobreak >nul
start "" "https://business.facebook.com/latest/whatsapp_manager"
timeout /t 1 /nobreak >nul
start "" "https://developers.facebook.com/apps"
echo 5 tabs khul gayi. Pehle /select wali tab me existing portfolio kholo.
pause
goto menu
