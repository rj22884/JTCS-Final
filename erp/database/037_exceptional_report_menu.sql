/*
    Add top-level "Exceptional Report" menu after Stock.
    Sub-menus can be added later from Settings / Menu Management.
*/
USE JTCSS;
GO

SET NOCOUNT ON;
GO

IF NOT EXISTS (
    SELECT 1
    FROM dbo.MenuMaster
    WHERE MenuName = N'Exceptional Report'
      AND ParentMenuID IS NULL
)
BEGIN
    INSERT INTO dbo.MenuMaster (
        ParentMenuID,
        MenuName,
        MenuIcon,
        MenuURL,
        DisplayOrder,
        Description,
        IsActive,
        RoleName
    )
    VALUES (
        NULL,
        N'Exceptional Report',
        N'bi-clipboard-data',
        N'/exceptional-report/stamp-certificate',
        28,
        N'Exceptional and special reports',
        1,
        NULL
    );
END
ELSE
BEGIN
    UPDATE dbo.MenuMaster
    SET MenuIcon = N'bi-clipboard-data',
        MenuURL = N'/exceptional-report/stamp-certificate',
        DisplayOrder = 28,
        Description = N'Exceptional and special reports',
        IsActive = 1
    WHERE MenuName = N'Exceptional Report'
      AND ParentMenuID IS NULL;
END;
GO

PRINT '037_exceptional_report_menu.sql completed.';
GO
