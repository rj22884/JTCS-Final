USE JTCSS;
GO

IF OBJECT_ID(N'dbo.CustomerGroupMaster', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.CustomerGroupMaster (
        GroupID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        GroupCode NVARCHAR(20) NOT NULL,
        GroupName NVARCHAR(100) NOT NULL,
        TabCodes NVARCHAR(500) NOT NULL,
        DisplayOrder INT NOT NULL CONSTRAINT DF_CustomerGroupMaster_DisplayOrder DEFAULT (1),
        ActiveStatus BIT NOT NULL CONSTRAINT DF_CustomerGroupMaster_ActiveStatus DEFAULT (1),
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_CustomerGroupMaster_CreatedDate DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT UX_CustomerGroupMaster_GroupCode UNIQUE (GroupCode)
    );
END;
GO

MERGE dbo.CustomerGroupMaster AS t
USING (
    VALUES
        (N'ITR', N'ITR', N'basic,contact,address,itr,bank,social', 1),
        (N'TDS', N'TDS', N'basic,contact,address,tds,compliance,bank', 2),
        (N'GST', N'GST', N'basic,contact,address,gst,business,bank', 3),
        (N'DSC', N'DSC', N'basic,contact,address,dsc,bank', 4)
) AS s (GroupCode, GroupName, TabCodes, DisplayOrder)
ON t.GroupCode = s.GroupCode
WHEN NOT MATCHED THEN
    INSERT (GroupCode, GroupName, TabCodes, DisplayOrder)
    VALUES (s.GroupCode, s.GroupName, s.TabCodes, s.DisplayOrder)
WHEN MATCHED THEN
    UPDATE SET GroupName = s.GroupName, TabCodes = s.TabCodes, DisplayOrder = s.DisplayOrder;
GO

DECLARE @MastersID INT = (SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Masters' AND ParentMenuID IS NULL);

IF @MastersID IS NOT NULL
BEGIN
    IF NOT EXISTS (SELECT 1 FROM dbo.MenuMaster WHERE MenuName IN (N'Group Master', N'Customer Group Master') AND ParentMenuID = @MastersID)
        INSERT INTO dbo.MenuMaster (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive)
        VALUES (@MastersID, N'Customer Group Master', N'bi-collection', N'/masters/group', 4, N'Customer group master for Customer Master tabs', 1);
    ELSE
        UPDATE dbo.MenuMaster
        SET MenuName = N'Customer Group Master', MenuURL = N'/masters/group', MenuIcon = N'bi-collection', IsActive = 1,
            Description = N'Customer group master for Customer Master tabs'
        WHERE ParentMenuID = @MastersID
          AND MenuName IN (N'Group Master', N'Customer Group Master');
END;
GO

PRINT '032_customer_group_master.sql completed.';
GO
