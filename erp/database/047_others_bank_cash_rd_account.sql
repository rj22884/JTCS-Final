/*
    Other Bank/Cash Transactions + RD Account Master

    Do NOT re-add CK_JtcsBankAccountMaster_AccountType — production uses many
    AccountType codes (CA-Current Account, etc.). Source of truth is
    AccountTypeMaster (057_account_type_master.sql).
*/
USE JTCSS;
GO

-- Drop legacy restrictive CHECK if present
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

IF OBJECT_ID(N'dbo.RdAccountMaster', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.RdAccountMaster (
        RdAccountID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        RdName NVARCHAR(150) NOT NULL,
        BankName NVARCHAR(150) NULL,
        RdNumber NVARCHAR(50) NOT NULL,
        BankAccountID INT NULL,
        OpeningDate DATE NULL,
        MaturityDate DATE NULL,
        InterestRate DECIMAL(9, 4) NULL,
        InstallmentAmount DECIMAL(18, 2) NULL,
        OpeningBalance DECIMAL(18, 2) NULL,
        ActiveStatus BIT NOT NULL CONSTRAINT DF_RdAccountMaster_Active DEFAULT (1),
        Remarks NVARCHAR(500) NULL,
        CreatedBy NVARCHAR(100) NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_RdAccountMaster_Created DEFAULT (SYSUTCDATETIME()),
        ModifiedDate DATETIME2 NULL,
        CONSTRAINT UX_RdAccountMaster_RdNumber UNIQUE (RdNumber),
        CONSTRAINT FK_RdAccountMaster_BankAccount
            FOREIGN KEY (BankAccountID) REFERENCES dbo.JtcsBankAccountMaster (JtcsBankAccountID)
    );
END;
GO

IF OBJECT_ID(N'dbo.OthersBankCashTransaction', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.OthersBankCashTransaction (
        EntryID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        VoucherNo NVARCHAR(50) NOT NULL,
        WorkDate DATE NOT NULL,
        Purpose NVARCHAR(200) NOT NULL,
        CreditBankAccountID INT NOT NULL,
        DebitBankAccountID INT NOT NULL,
        Amount DECIMAL(18, 2) NOT NULL,
        Remarks NVARCHAR(500) NULL,
        OutBankTransactionID INT NULL,
        InBankTransactionID INT NULL,
        CreatedBy NVARCHAR(100) NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_OthersBankCashTxn_Created DEFAULT (SYSUTCDATETIME()),
        IsActive BIT NOT NULL CONSTRAINT DF_OthersBankCashTxn_Active DEFAULT (1),
        CONSTRAINT UX_OthersBankCashTransaction_Voucher UNIQUE (VoucherNo),
        CONSTRAINT FK_OthersBankCashTxn_Credit
            FOREIGN KEY (CreditBankAccountID) REFERENCES dbo.JtcsBankAccountMaster (JtcsBankAccountID),
        CONSTRAINT FK_OthersBankCashTxn_Debit
            FOREIGN KEY (DebitBankAccountID) REFERENCES dbo.JtcsBankAccountMaster (JtcsBankAccountID),
        CONSTRAINT CK_OthersBankCashTxn_Accounts
            CHECK (CreditBankAccountID <> DebitBankAccountID),
        CONSTRAINT CK_OthersBankCashTxn_Amount
            CHECK (Amount > 0)
    );
    CREATE INDEX IX_OthersBankCashTxn_WorkDate
        ON dbo.OthersBankCashTransaction (WorkDate DESC, EntryID DESC);
END;
GO

-- Menus: Others child below Income/Expense (DisplayOrder 0), this at 1
DECLARE @OthersID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Others' AND ParentMenuID IS NULL
);

IF @OthersID IS NOT NULL
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM dbo.MenuMaster
        WHERE MenuName = N'Other Bank/Cash Transactions' AND ParentMenuID = @OthersID
    )
    BEGIN
        INSERT INTO dbo.MenuMaster (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
        VALUES (
            @OthersID,
            N'Other Bank/Cash Transactions',
            N'bi-arrow-left-right',
            N'/others/bank-cash-transactions',
            1,
            N'Double-entry bank/cash/RD transfers and journal',
            1,
            NULL
        );
    END
    ELSE
    BEGIN
        UPDATE dbo.MenuMaster
        SET MenuURL = N'/others/bank-cash-transactions',
            MenuIcon = N'bi-arrow-left-right',
            DisplayOrder = 1,
            Description = N'Double-entry bank/cash/RD transfers and journal',
            IsActive = 1
        WHERE MenuName = N'Other Bank/Cash Transactions' AND ParentMenuID = @OthersID;
    END
END;
GO

DECLARE @MastersID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Masters' AND ParentMenuID IS NULL
);

IF @MastersID IS NOT NULL
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM dbo.MenuMaster
        WHERE MenuName = N'RD Account' AND ParentMenuID = @MastersID
    )
    BEGIN
        INSERT INTO dbo.MenuMaster (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
        VALUES (
            @MastersID,
            N'RD Account',
            N'bi-piggy-bank',
            N'/masters/rd-account',
            6,
            N'Recurring deposit account master',
            1,
            NULL
        );
    END
    ELSE
    BEGIN
        UPDATE dbo.MenuMaster
        SET MenuURL = N'/masters/rd-account',
            MenuIcon = N'bi-piggy-bank',
            DisplayOrder = 6,
            Description = N'Recurring deposit account master',
            IsActive = 1
        WHERE MenuName = N'RD Account' AND ParentMenuID = @MastersID;
    END
END;
GO

PRINT '047_others_bank_cash_rd_account.sql completed.';
GO
