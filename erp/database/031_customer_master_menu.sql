USE JTCSS;
GO

IF COL_LENGTH(N'dbo.CustomerMaster', N'CustomerGroup') IS NULL
    ALTER TABLE dbo.CustomerMaster ADD CustomerGroup NVARCHAR(20) NULL;
GO

IF COL_LENGTH(N'dbo.CustomerMaster', N'IncomeTaxPassword') IS NULL
    ALTER TABLE dbo.CustomerMaster ADD IncomeTaxPassword NVARCHAR(20) NULL;
GO

DECLARE @MastersID INT = (SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Masters' AND ParentMenuID IS NULL);

IF @MastersID IS NOT NULL
BEGIN
    IF NOT EXISTS (SELECT 1 FROM dbo.MenuMaster WHERE MenuName = N'Customer Master' AND ParentMenuID = @MastersID)
        INSERT INTO dbo.MenuMaster (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive)
        VALUES (@MastersID, N'Customer Master', N'bi-person-vcard', N'/masters/customer', 5, N'Customer master with group-wise tabs', 1);
    ELSE
        UPDATE dbo.MenuMaster
        SET MenuURL = N'/masters/customer', MenuIcon = N'bi-person-vcard', IsActive = 1,
            Description = N'Customer master with group-wise tabs'
        WHERE MenuName = N'Customer Master' AND ParentMenuID = @MastersID;
END;
GO

PRINT '031_customer_master_menu.sql completed.';
GO
