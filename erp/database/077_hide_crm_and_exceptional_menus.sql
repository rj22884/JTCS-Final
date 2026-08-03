/*
    Hide CRM + Exceptional Report from ERP navigation (separate apps).
    Keeps MenuMaster rows; only sets IsActive = 0. DATA safe.
*/
USE JTCSS;
GO

UPDATE dbo.MenuMaster
SET IsActive = 0,
    Description = CASE
        WHEN MenuName = N'CRM' AND ParentMenuID IS NULL
            THEN N'Customer Relationship Management (moved to separate app)'
        ELSE Description
    END
WHERE (MenuName = N'CRM' AND ParentMenuID IS NULL)
   OR MenuURL LIKE N'/crm/%'
   OR ParentMenuID IN (
        SELECT MenuID FROM dbo.MenuMaster
        WHERE MenuName = N'CRM' AND ParentMenuID IS NULL
   );

UPDATE dbo.MenuMaster
SET IsActive = 0
WHERE MenuName IN (N'Exceptional Report', N'Stamp Exception', N'E-Court Exception')
   OR MenuURL = N'/exceptional-report'
   OR MenuURL LIKE N'/exceptional-report/%';

PRINT '077_hide_crm_and_exceptional_menus.sql completed.';
GO
