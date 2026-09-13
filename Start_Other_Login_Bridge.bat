@echo off
title JTCS Other Login Bridge
cd /d "%~dp0"

echo.
echo  JTCS Other Login Bridge
echo  Data: E:\Web-Data
echo.

call "%~dp0scripts\install_other_login_bridge_startup.bat"
call "%~dp0scripts\run_other_login_bridge.bat"

echo.
echo  Computer ON  = all Other Logins enabled on local + VPS
echo  Computer OFF = all Other Logins disabled
echo  Token file   = E:\Web-Data\_bridge\token.txt
echo  Put the same token on VPS as OTHER_LOGIN_BRIDGE_TOKEN
echo.
pause
