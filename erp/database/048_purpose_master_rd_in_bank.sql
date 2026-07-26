/*
    Deactivate separate RD Account menu (RD lives in Bank Master as AccountType=RD).
    Create Purpose Master for Other Bank/Cash Transactions.
*/
USE JTCSS;
GO

UPDATE dbo.MenuMaster
SET IsActive = 0,
    Description = N'Deprecated — use Bank Master with Account Type RD'
WHERE MenuName = N'RD Account'
  AND ParentMenuID IS NOT NULL;
GO

IF OBJECT_ID(N'dbo.PurposeMaster', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.PurposeMaster (
        PurposeID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        PurposeName NVARCHAR(200) NOT NULL,
        Description NVARCHAR(500) NULL,
        ActiveStatus BIT NOT NULL CONSTRAINT DF_PurposeMaster_Active DEFAULT (1),
        CreatedBy NVARCHAR(100) NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_PurposeMaster_Created DEFAULT (SYSUTCDATETIME()),
        ModifiedDate DATETIME2 NULL,
        CONSTRAINT UX_PurposeMaster_PurposeName UNIQUE (PurposeName)
    );
END;
GO

IF NOT EXISTS (SELECT 1 FROM dbo.PurposeMaster WHERE PurposeName = N'Investment in RDs')
BEGIN
    INSERT INTO dbo.PurposeMaster (PurposeName, Description, ActiveStatus, CreatedBy)
    VALUES (N'Investment in RDs', N'Transfer / investment into RD account', 1, N'system');
END;
GO

IF NOT EXISTS (SELECT 1 FROM dbo.PurposeMaster WHERE PurposeName = N'Bank Transfer')
BEGIN
    INSERT INTO dbo.PurposeMaster (PurposeName, Description, ActiveStatus, CreatedBy)
    VALUES (N'Bank Transfer', N'Account to account transfer', 1, N'system');
END;
GO

IF NOT EXISTS (SELECT 1 FROM dbo.PurposeMaster WHERE PurposeName = N'Cash Deposit')
BEGIN
    INSERT INTO dbo.PurposeMaster (PurposeName, Description, ActiveStatus, CreatedBy)
    VALUES (N'Cash Deposit', N'Cash deposited into bank', 1, N'system');
END;
GO

IF NOT EXISTS (SELECT 1 FROM dbo.PurposeMaster WHERE PurposeName = N'Cash Withdrawal')
BEGIN
    INSERT INTO dbo.PurposeMaster (PurposeName, Description, ActiveStatus, CreatedBy)
    VALUES (N'Cash Withdrawal', N'Cash withdrawn from bank', 1, N'system');
END;
GO

DECLARE @MastersID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Masters' AND ParentMenuID IS NULL
);

IF @MastersID IS NOT NULL
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM dbo.MenuMaster
        WHERE MenuName = N'Purpose Master' AND ParentMenuID = @MastersID
    )
    BEGIN
        INSERT INTO dbo.MenuMaster (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
        VALUES (
            @MastersID,
            N'Purpose Master',
            N'bi-list-check',
            N'/masters/purpose',
            6,
            N'Purpose list for Other Bank/Cash Transactions',
            1,
            NULL
        );
    END
    ELSE
    BEGIN
        UPDATE dbo.MenuMaster
        SET MenuURL = N'/masters/purpose',
            MenuIcon = N'bi-list-check',
            DisplayOrder = 6,
            Description = N'Purpose list for Other Bank/Cash Transactions',
            IsActive = 1
        WHERE MenuName = N'Purpose Master' AND ParentMenuID = @MastersID;
    END
END;
GO

PRINT '048_purpose_master_rd_in_bank.sql completed.';
GO
