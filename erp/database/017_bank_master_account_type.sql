/*
    Bank Master — AccountType column + Masters menu entry
*/
USE JTCSS;
GO

IF COL_LENGTH(N'dbo.JtcsBankAccountMaster', N'AccountType') IS NULL
BEGIN
    ALTER TABLE dbo.JtcsBankAccountMaster
    ADD AccountType NVARCHAR(10) NULL;
END;
GO

UPDATE dbo.JtcsBankAccountMaster
SET AccountType = N'OTH'
WHERE AccountType IS NULL OR LTRIM(RTRIM(AccountType)) = N'';
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.check_constraints
    WHERE name = N'CK_JtcsBankAccountMaster_AccountType'
)
BEGIN
    ALTER TABLE dbo.JtcsBankAccountMaster
    ADD CONSTRAINT CK_JtcsBankAccountMaster_AccountType
        CHECK (AccountType IS NULL OR AccountType IN (N'SB', N'CC/OD', N'OTH'));
END;
GO

DECLARE @MastersID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Masters' AND ParentMenuID IS NULL
);

IF @MastersID IS NULL
BEGIN
    INSERT INTO dbo.MenuMaster (MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
    VALUES (N'Masters', N'bi-database', N'/masters', 5, N'Master data management', 1, NULL);
    SET @MastersID = SCOPE_IDENTITY();
END;

IF NOT EXISTS (
    SELECT 1 FROM dbo.MenuMaster WHERE MenuName = N'Bank Master' AND ParentMenuID = @MastersID
)
BEGIN
    INSERT INTO dbo.MenuMaster (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
    VALUES (
        @MastersID,
        N'Bank Master',
        N'bi-bank',
        N'/masters/bank',
        1,
        N'Bank account master (JtcsBankAccountMaster)',
        1,
        NULL
    );
END
ELSE
BEGIN
    UPDATE dbo.MenuMaster
    SET MenuURL = N'/masters/bank',
        MenuIcon = N'bi-bank',
        Description = N'Bank account master (JtcsBankAccountMaster)',
        IsActive = 1
    WHERE MenuName = N'Bank Master' AND ParentMenuID = @MastersID;
END;
GO

PRINT '017_bank_master_account_type.sql completed.';
GO
