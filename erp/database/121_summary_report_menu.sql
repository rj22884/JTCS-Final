/* Add Summary before Daily Collection in Reports. Idempotent menu-only migration. */
DECLARE @ReportsID INT;

SELECT TOP 1 @ReportsID = r.MenuID
FROM dbo.MenuMaster r
WHERE r.MenuName IN (N'Reports', N'Reports and Analysis', N'Reports & Analysis')
  AND ISNULL(r.IsActive, 1) = 1
ORDER BY CASE WHEN EXISTS (
             SELECT 1 FROM dbo.MenuMaster c
             WHERE c.ParentMenuID = r.MenuID
               AND c.MenuName = N'Daily Collection'
               AND ISNULL(c.IsActive, 1) = 1
         ) THEN 0
         WHEN r.ParentMenuID IS NOT NULL THEN 1
         WHEN r.MenuURL = N'/accounting/reports' THEN 2
         ELSE 3 END,
         r.MenuID;

IF @ReportsID IS NOT NULL
BEGIN
    IF EXISTS (SELECT 1 FROM dbo.MenuMaster WHERE MenuURL = N'/reports/summary')
        UPDATE dbo.MenuMaster
        SET ParentMenuID = @ReportsID,
            MenuName = N'Summary',
            MenuIcon = N'bi-search',
            DisplayOrder = 0,
            Description = N'Search ledgers and view date-wise linked details',
            IsActive = 1
        WHERE MenuURL = N'/reports/summary';
    ELSE
        INSERT INTO dbo.MenuMaster
            (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
        VALUES
            (@ReportsID, N'Summary', N'bi-search', N'/reports/summary', 0,
             N'Search ledgers and view date-wise linked details', 1, NULL);
END;
