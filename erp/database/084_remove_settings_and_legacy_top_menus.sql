/*
    Permanently remove:
      - Admin Role → Settings (customized Menu Management /admin/menus)
      - Top-level modules except core ERP + Accounting:
          ITR, Others, GST, DSC, TDS, Payroll, Transactions, Employee, Stock, …

    Keep top-level active:
      Admin Role, Dashboard, Activities, Reports and Analysis, Masters, Accounting

    DATA safe — MenuMaster.IsActive / Description only.
*/
USE JTCSS;
GO

SET NOCOUNT ON;
GO

UPDATE dbo.MenuMaster
SET IsActive = 0,
    Description = CASE
        WHEN Description LIKE N'%core ERP nav%' THEN Description
        ELSE LEFT(CONCAT(ISNULL(Description, N''), N' (hidden from core ERP nav)'), 300)
    END
WHERE ParentMenuID IS NULL
  AND MenuName NOT IN (
        N'Admin Role',
        N'Dashboard',
        N'Activities',
        N'Reports and Analysis',
        N'Masters',
        N'Accounting'
  );
GO

UPDATE dbo.MenuMaster
SET IsActive = 0
WHERE ParentMenuID IS NULL
  AND MenuName IN (
        N'ITR', N'Others', N'GST', N'DSC', N'TDS',
        N'Payroll', N'Transactions', N'Employee', N'Stock',
        N'Menu Management', N'Settings', N'CRM'
  );
GO

/* Admin Role → Settings / Menu Management — permanently off */
UPDATE dbo.MenuMaster
SET IsActive = 0,
    Description = N'Removed — customized menu disabled'
WHERE MenuName IN (N'Settings', N'Menu Management', N'Menu Admin')
   OR LOWER(ISNULL(MenuURL, N'')) IN (N'/admin/menus', N'/admin/menus/', N'/settings', N'/settings/');
GO

UPDATE dbo.MenuMaster
SET IsActive = 0
WHERE MenuName IN (N'Logout', N'Log Out')
   OR LOWER(ISNULL(MenuURL, N'')) IN (N'/logout', N'/auth/logout');
GO

PRINT '084_remove_settings_and_legacy_top_menus.sql completed.';
GO
