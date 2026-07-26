/*
    Update stamp report menu labels
*/
SET NOCOUNT ON;

DECLARE @ReportsID INT = (SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Reports' AND ParentMenuID IS NULL);

IF @ReportsID IS NOT NULL
BEGIN
    UPDATE dbo.MenuMaster SET MenuName = N'Daily Stamp Sale', MenuURL = N'/reports/stamp-daily-sale', IsActive = 1
    WHERE ParentMenuID = @ReportsID AND MenuName = N'Stamp Sales';

    IF NOT EXISTS (SELECT 1 FROM dbo.MenuMaster WHERE ParentMenuID = @ReportsID AND MenuURL = N'/reports/stamp-certificate-wise')
        INSERT INTO dbo.MenuMaster (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
        VALUES (@ReportsID, N'Certificate Wise', N'bi-file-earmark-text', N'/reports/stamp-certificate-wise', 26,
                N'SHCIL certificate wise stamp report', 1, NULL);
END;
GO

PRINT '013_stamp_reports_menu.sql completed.';
GO
