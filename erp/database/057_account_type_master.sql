/*
    Account Type Master + seed SB / CC/OD / OTH / RD
    Drop hard-coded CHECK on JtcsBankAccountMaster.AccountType (validate via master).
*/
USE JTCSS;
GO

IF OBJECT_ID(N'dbo.AccountTypeMaster', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.AccountTypeMaster (
        AccountTypeID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        AccountTypeCode NVARCHAR(20) NOT NULL,
        AccountTypeName NVARCHAR(100) NOT NULL,
        Description NVARCHAR(255) NULL,
        OrderNo INT NOT NULL CONSTRAINT DF_AccountTypeMaster_OrderNo DEFAULT (100),
        IsActive BIT NOT NULL CONSTRAINT DF_AccountTypeMaster_IsActive DEFAULT (1),
        CreatedAt DATETIME2 NOT NULL CONSTRAINT DF_AccountTypeMaster_CreatedAt DEFAULT (SYSUTCDATETIME()),
        UpdatedAt DATETIME2 NULL,
        CONSTRAINT UX_AccountTypeMaster_Code UNIQUE (AccountTypeCode)
    );
    CREATE INDEX IX_AccountTypeMaster_Active_Order
        ON dbo.AccountTypeMaster (IsActive, OrderNo, AccountTypeCode);
END;
GO

/* Seed codes used by Bank Master + common account types */
MERGE dbo.AccountTypeMaster AS t
USING (
    SELECT * FROM (VALUES
        (N'CA-Current Asset',   N'Current Asset',              N'Current asset bank account', 1),
        (N'CA-Current Account', N'Current Account',            N'Current account', 2),
        (N'SB',                 N'Savings Bank',               N'Savings bank account', 3),
        (N'CC/OD',              N'Cash Credit / Overdraft',    N'Cash credit or overdraft', 4),
        (N'LN-Loan Account',    N'Loan Account',               N'Loan account', 5),
        (N'DA-Demat Account',   N'Demat Account',              N'Demat account', 6),
        (N'OTH',                N'Other',                      N'Other account type', 7),
        (N'RD',                 N'Recurring Deposit',          N'Recurring deposit account', 8)
    ) AS v(AccountTypeCode, AccountTypeName, Description, OrderNo)
) AS s
ON t.AccountTypeCode = s.AccountTypeCode
WHEN NOT MATCHED THEN
    INSERT (AccountTypeCode, AccountTypeName, Description, OrderNo, IsActive)
    VALUES (s.AccountTypeCode, s.AccountTypeName, s.Description, s.OrderNo, 1);
GO

/* Sync any AccountType already stored on bank accounts */
INSERT INTO dbo.AccountTypeMaster
    (AccountTypeCode, AccountTypeName, Description, OrderNo, IsActive)
SELECT DISTINCT
    LTRIM(RTRIM(b.AccountType)),
    LTRIM(RTRIM(b.AccountType)),
    N'Synced from Bank Master',
    200,
    1
FROM dbo.JtcsBankAccountMaster b
WHERE b.AccountType IS NOT NULL
  AND LTRIM(RTRIM(b.AccountType)) <> N''
  AND NOT EXISTS (
      SELECT 1
      FROM dbo.AccountTypeMaster t
      WHERE t.AccountTypeCode = LTRIM(RTRIM(b.AccountType))
  );
GO

/* Allow future codes from master (keep existing bank AccountType values intact) */
IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = N'CK_JtcsBankAccountMaster_AccountType'
      AND parent_object_id = OBJECT_ID(N'dbo.JtcsBankAccountMaster')
)
BEGIN
    ALTER TABLE dbo.JtcsBankAccountMaster
    DROP CONSTRAINT CK_JtcsBankAccountMaster_AccountType;
END;
GO

IF COL_LENGTH(N'dbo.JtcsBankAccountMaster', N'AccountType') IS NOT NULL
BEGIN
    ALTER TABLE dbo.JtcsBankAccountMaster ALTER COLUMN AccountType NVARCHAR(20) NULL;
END;
GO

DECLARE @MastersID INT;
SELECT TOP 1 @MastersID = MenuID
FROM dbo.MenuMaster
WHERE MenuName = N'Masters' AND ParentMenuID IS NULL
ORDER BY MenuID;

IF @MastersID IS NOT NULL
BEGIN
    IF EXISTS (
        SELECT 1 FROM dbo.MenuMaster
        WHERE ParentMenuID = @MastersID AND MenuName = N'Account Type Master'
    )
    BEGIN
        UPDATE dbo.MenuMaster
        SET MenuURL = N'/masters/account-type',
            MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-tags'),
            DisplayOrder = 18,
            Description = N'Bank account types (SB, CC/OD, OTH, RD, …)',
            IsActive = 1
        WHERE ParentMenuID = @MastersID AND MenuName = N'Account Type Master';
    END
    ELSE
    BEGIN
        INSERT INTO dbo.MenuMaster (
            ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
            Description, IsActive, RoleName
        )
        VALUES (
            @MastersID,
            N'Account Type Master',
            N'bi-tags',
            N'/masters/account-type',
            18,
            N'Bank account types (SB, CC/OD, OTH, RD, …)',
            1,
            NULL
        );
    END
END;
GO

PRINT '057_account_type_master.sql completed.';
GO
