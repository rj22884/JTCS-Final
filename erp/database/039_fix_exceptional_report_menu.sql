/*
    Fix Exceptional Report menu placement and working URL.
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
DECLARE @KeepID INT;

UPDATE dbo.MenuMaster
SET ParentMenuID = NULL,
    DisplayOrder = @TargetOrder,
    MenuURL = N'/exceptional-report/stamp-certificate',
    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-clipboard-data'),
    Description = COALESCE(Description, N'Exceptional and special reports'),
    IsActive = 1
WHERE MenuName = N'Exceptional Report'
  AND ParentMenuID IS NOT NULL;

SELECT TOP 1 @KeepID = MenuID
FROM dbo.MenuMaster
WHERE MenuName = N'Exceptional Report'
  AND ParentMenuID IS NULL
ORDER BY MenuID;

IF @KeepID IS NULL
BEGIN
    INSERT INTO dbo.MenuMaster (
        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName
    )
    VALUES (
        NULL,
        N'Exceptional Report',
        N'bi-clipboard-data',
        N'/exceptional-report/stamp-certificate',
        @TargetOrder,
        N'Exceptional and special reports',
        1,
        NULL
    );
    SET @KeepID = SCOPE_IDENTITY();
END
ELSE
BEGIN
    UPDATE dbo.MenuMaster
    SET DisplayOrder = @TargetOrder,
        MenuURL = N'/exceptional-report/stamp-certificate',
        MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-clipboard-data'),
        Description = COALESCE(Description, N'Exceptional and special reports'),
        IsActive = 1
    WHERE MenuID = @KeepID;
END;

UPDATE dbo.MenuMaster
SET IsActive = 0
WHERE MenuName = N'Exceptional Report'
  AND ParentMenuID IS NULL
  AND MenuID <> @KeepID;
GO

PRINT '039_fix_exceptional_report_menu.sql completed.';
GO
