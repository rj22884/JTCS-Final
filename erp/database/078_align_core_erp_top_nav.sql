/*
    Align top navigation with local ERP UI.

    Keep only these top-level menus active:
      Admin Role, Dashboard, Activities, Reports and Analysis,
      Masters, Accounting, Others

    Everything else at top level (ITR, GST, DSC, TDS, Payroll, Menu Management,
    Transactions, Employee, Stock, Settings, Logout, CRM, …) is hidden.
    Child menus under Admin Role / Activities / etc. stay as-is.
    DATA safe — MenuMaster.IsActive only.
*/
USE JTCSS;
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
        N'Accounting',
        N'Others'
  );
GO

UPDATE dbo.MenuMaster
SET IsActive = 0
WHERE MenuName IN (N'Logout', N'Log Out')
   OR LOWER(ISNULL(MenuURL, N'')) IN (N'/logout', N'/auth/logout');
GO

/* Keep CRM / exceptional hidden (belt-and-suspenders with 077) */
UPDATE dbo.MenuMaster
SET IsActive = 0
WHERE (MenuName = N'CRM' AND ParentMenuID IS NULL)
   OR MenuURL LIKE N'/crm/%'
   OR MenuName IN (N'Exceptional Report', N'Stamp Exception', N'E-Court Exception')
   OR MenuURL LIKE N'/exceptional-report/%';
GO

PRINT '078_align_core_erp_top_nav.sql completed.';
GO
