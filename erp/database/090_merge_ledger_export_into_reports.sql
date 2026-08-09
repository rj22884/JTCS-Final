/*
    Merge duplicate Admin → Import/Export → Ledger Export into
    Reports and Analysis → Ledger Report (preview / PDF / Excel).
*/
USE JTCSS;
GO

DECLARE @AdminRoleID INT;
DECLARE @ImportExportID INT;
DECLARE @ExportID INT;
DECLARE @ReportsID INT;

SELECT TOP 1 @AdminRoleID = MenuID
FROM dbo.MenuMaster
WHERE MenuName = N'Admin Role' AND ParentMenuID IS NULL
ORDER BY MenuID;

SELECT TOP 1 @ReportsID = MenuID
FROM dbo.MenuMaster
WHERE ParentMenuID IS NULL
  AND MenuName IN (N'Reports and Analysis', N'Reports & Analysis', N'Reports')
ORDER BY
    CASE MenuName
        WHEN N'Reports and Analysis' THEN 0
        WHEN N'Reports & Analysis' THEN 1
        ELSE 2
    END,
    MenuID;

IF @ReportsID IS NOT NULL
BEGIN
    UPDATE dbo.MenuMaster
    SET MenuName = N'Reports and Analysis',
        IsActive = 1,
        MenuURL = NULL
    WHERE MenuID = @ReportsID;

    IF EXISTS (
        SELECT 1 FROM dbo.MenuMaster
        WHERE ParentMenuID = @ReportsID AND MenuName = N'Ledger Report'
    )
        UPDATE dbo.MenuMaster
        SET MenuURL = N'/Reports_and_analysis/ledger_report',
            MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-journal-text'),
            Description = N'Search and preview bank, customer, work/category and item ledgers',
            IsActive = 1
        WHERE ParentMenuID = @ReportsID AND MenuName = N'Ledger Report';
    ELSE
        INSERT INTO dbo.MenuMaster (
            ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
            Description, IsActive, RoleName
        )
        VALUES (
            @ReportsID,
            N'Ledger Report',
            N'bi-journal-text',
            N'/Reports_and_analysis/ledger_report',
            1,
            N'Search and preview bank, customer, work/category and item ledgers',
            1,
            NULL
        );
END;

SELECT TOP 1 @ImportExportID = MenuID
FROM dbo.MenuMaster
WHERE @AdminRoleID IS NOT NULL
  AND ParentMenuID = @AdminRoleID
  AND MenuName = N'Import/Export'
ORDER BY MenuID;

SELECT TOP 1 @ExportID = MenuID
FROM dbo.MenuMaster
WHERE @ImportExportID IS NOT NULL
  AND ParentMenuID = @ImportExportID
  AND MenuName = N'Export'
ORDER BY MenuID;

UPDATE dbo.MenuMaster
SET IsActive = 0,
    Description = N'Merged into Reports and Analysis → Ledger Report'
WHERE MenuURL = N'/admin/import-export/ledger'
   OR (
        @ExportID IS NOT NULL
        AND ParentMenuID = @ExportID
        AND MenuName = N'Ledger Export'
   );

IF @ExportID IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM dbo.MenuMaster
        WHERE ParentMenuID = @ExportID
          AND ISNULL(IsActive, 0) = 1
          AND MenuName <> N'Ledger Export'
   )
    UPDATE dbo.MenuMaster
    SET IsActive = 0,
        Description = N'Merged into Reports and Analysis → Ledger Report'
    WHERE MenuID = @ExportID;

IF @ImportExportID IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM dbo.MenuMaster
        WHERE ParentMenuID = @ImportExportID
          AND ISNULL(IsActive, 0) = 1
   )
    UPDATE dbo.MenuMaster
    SET IsActive = 0,
        Description = N'Merged into Reports and Analysis → Ledger Report'
    WHERE MenuID = @ImportExportID;
GO
