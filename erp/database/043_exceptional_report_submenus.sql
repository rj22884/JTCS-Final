/*
    Exceptional Report sub-menus:
      1. Stamp Exception  -> /exceptional-report/stamp-certificate
      2. e-Court Exception -> /exceptional-report/ecourt-exception (placeholder)
*/
USE JTCSS;
GO

SET NOCOUNT ON;
GO

DECLARE @StockOrder INT = (
    SELECT TOP 1 DisplayOrder FROM dbo.MenuMaster
    WHERE MenuName = N'Stock' AND ParentMenuID IS NULL
);
DECLARE @TargetOrder INT = ISNULL(@StockOrder, 27) + 1;
DECLARE @ParentID INT;

/* Ensure top-level Exceptional Report (dropdown parent, no direct URL) */
SELECT TOP 1 @ParentID = MenuID
FROM dbo.MenuMaster
WHERE MenuName = N'Exceptional Report'
  AND ParentMenuID IS NULL
ORDER BY MenuID;

IF @ParentID IS NULL
BEGIN
    INSERT INTO dbo.MenuMaster (
        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName
    )
    VALUES (
        NULL,
        N'Exceptional Report',
        N'bi-clipboard-data',
        NULL,
        @TargetOrder,
        N'Exceptional and special reports',
        1,
        NULL
    );
    SET @ParentID = SCOPE_IDENTITY();
END
ELSE
BEGIN
    UPDATE dbo.MenuMaster
    SET DisplayOrder = @TargetOrder,
        MenuURL = NULL,
        MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-clipboard-data'),
        Description = COALESCE(Description, N'Exceptional and special reports'),
        IsActive = 1
    WHERE MenuID = @ParentID;
END;

/* Deactivate duplicate top-level Exceptional Report rows */
UPDATE dbo.MenuMaster
SET IsActive = 0
WHERE MenuName = N'Exceptional Report'
  AND ParentMenuID IS NULL
  AND MenuID <> @ParentID;

/* Rename old Stamp Certificate Reconciliation -> Stamp Exception */
UPDATE dbo.MenuMaster
SET MenuName = N'Stamp Exception',
    MenuIcon = N'bi-file-earmark-spreadsheet',
    MenuURL = N'/exceptional-report/stamp-certificate',
    DisplayOrder = 1,
    Description = N'SHCIL stamp certificate reconciliation',
    IsActive = 1,
    ParentMenuID = @ParentID
WHERE ParentMenuID = @ParentID
  AND (
      MenuURL = N'/exceptional-report/stamp-certificate'
      OR MenuName IN (N'Stamp Certificate Reconciliation', N'Stamp Exception')
  );

IF NOT EXISTS (
    SELECT 1 FROM dbo.MenuMaster
    WHERE ParentMenuID = @ParentID
      AND MenuURL = N'/exceptional-report/stamp-certificate'
)
BEGIN
    INSERT INTO dbo.MenuMaster (
        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName
    )
    VALUES (
        @ParentID,
        N'Stamp Exception',
        N'bi-file-earmark-spreadsheet',
        N'/exceptional-report/stamp-certificate',
        1,
        N'SHCIL stamp certificate reconciliation',
        1,
        NULL
    );
END;

/* e-Court Exception placeholder submenu */
IF NOT EXISTS (
    SELECT 1 FROM dbo.MenuMaster
    WHERE ParentMenuID = @ParentID
      AND (
          MenuURL = N'/exceptional-report/ecourt-exception'
          OR MenuName = N'e-Court Exception'
      )
)
BEGIN
    INSERT INTO dbo.MenuMaster (
        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName
    )
    VALUES (
        @ParentID,
        N'e-Court Exception',
        N'bi-journal-check',
        N'/exceptional-report/ecourt-exception',
        2,
        N'e-Court exceptional report (coming soon)',
        1,
        NULL
    );
END
ELSE
BEGIN
    UPDATE dbo.MenuMaster
    SET MenuName = N'e-Court Exception',
        MenuIcon = N'bi-journal-check',
        MenuURL = N'/exceptional-report/ecourt-exception',
        DisplayOrder = 2,
        Description = N'e-Court exceptional report (coming soon)',
        IsActive = 1,
        ParentMenuID = @ParentID
    WHERE ParentMenuID = @ParentID
      AND (
          MenuURL = N'/exceptional-report/ecourt-exception'
          OR MenuName = N'e-Court Exception'
      );
END;
GO

PRINT '043_exceptional_report_submenus.sql completed.';
GO
