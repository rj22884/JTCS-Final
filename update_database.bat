@echo off
title JTCS ERP - Database Update (JTCSS)
setlocal
cd /d "%~dp0erp\database"
echo Applying database migrations to JTCSS...
set DB=JTCSS
set SRV=JTCS\JTCS
for %%F in (
    015_bootstrap_jtcss_legacy_structure.sql
    001_create_menu_master.sql
    002_create_jtcs_daily_transaction.sql
    004_auth_production.sql
    008_create_password_reset_otp.sql
    009_add_verification_tracking.sql
    010_create_stamp_master.sql
    012_stamp_ocr_image.sql
    014_multiple_payment_modes.sql
    003_seed_module_menus.sql
    005_remove_court_fee_stamp.sql
    011_stamp_activity_menu.sql
    013_stamp_reports_menu.sql
) do (
    echo Running %%F...
    sqlcmd -S "%SRV%" -d %DB% -E -i "%%F"
    if errorlevel 1 (
        echo FAILED on %%F. Check SQL Server connection %SRV%
        pause
        exit /b 1
    )
)
echo Done. Restart start_jtcs_erp.bat
pause
endlocal
