/*
    JTCS ERP - Chart of Group Master + Chart of Account Master (Tally-style)
    Idempotent create + seed of List of Groups.
*/

SET NOCOUNT ON;
GO

IF OBJECT_ID(N'dbo.ChartOfGroupMaster', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ChartOfGroupMaster (
        GroupID       INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        GroupName     NVARCHAR(150) NOT NULL,
        UnderType     NVARCHAR(20)  NOT NULL,
        IsActive      BIT NOT NULL CONSTRAINT DF_ChartOfGroupMaster_IsActive DEFAULT (1),
        CreatedDate   DATETIME2 NOT NULL CONSTRAINT DF_ChartOfGroupMaster_Created DEFAULT (SYSUTCDATETIME()),
        UpdatedDate   DATETIME2 NULL,
        CONSTRAINT CK_ChartOfGroupMaster_UnderType CHECK (UnderType IN (N'Assets', N'Liabilities')),
        CONSTRAINT UX_ChartOfGroupMaster_GroupName UNIQUE (GroupName)
    );
END
GO

IF OBJECT_ID(N'dbo.ChartOfAccountMaster', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ChartOfAccountMaster (
        AccountID     INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        AccountName   NVARCHAR(200) NOT NULL,
        GroupID       INT NOT NULL,
        IsActive      BIT NOT NULL CONSTRAINT DF_ChartOfAccountMaster_IsActive DEFAULT (1),
        CreatedDate   DATETIME2 NOT NULL CONSTRAINT DF_ChartOfAccountMaster_Created DEFAULT (SYSUTCDATETIME()),
        UpdatedDate   DATETIME2 NULL,
        CONSTRAINT FK_ChartOfAccountMaster_Group
            FOREIGN KEY (GroupID) REFERENCES dbo.ChartOfGroupMaster (GroupID),
        CONSTRAINT UX_ChartOfAccountMaster_AccountName UNIQUE (AccountName)
    );
    CREATE INDEX IX_ChartOfAccountMaster_GroupID ON dbo.ChartOfAccountMaster (GroupID);
END
GO

/* Seed Tally List of Groups (Assets / Liabilities only) */
DECLARE @Seed TABLE (GroupName NVARCHAR(150) NOT NULL, UnderType NVARCHAR(20) NOT NULL);
INSERT INTO @Seed (GroupName, UnderType) VALUES
 (N'Bank Accounts', N'Assets'),
 (N'Bank OCC A/c', N'Assets'),
 (N'Bank OD A/c', N'Liabilities'),
 (N'Branch / Divisions', N'Liabilities'),
 (N'Capital Account', N'Liabilities'),
 (N'Cash-in-Hand', N'Assets'),
 (N'Commission Income', N'Liabilities'),
 (N'Computers Printers & Electric Items', N'Assets'),
 (N'Current Assets', N'Assets'),
 (N'Current Liabilities', N'Liabilities'),
 (N'Deposits (Asset)', N'Assets'),
 (N'Direct Expenses', N'Assets'),
 (N'Direct Incomes', N'Liabilities'),
 (N'Duties & Taxes', N'Liabilities'),
 (N'Electricity Expenses', N'Assets'),
 (N'Expenses (Direct)', N'Assets'),
 (N'Expenses (Indirect)', N'Assets'),
 (N'Fixed Assets', N'Assets'),
 (N'Immovable Property', N'Assets'),
 (N'Income (Direct)', N'Liabilities'),
 (N'Income (Indirect)', N'Liabilities'),
 (N'Indirect Expenses', N'Assets'),
 (N'Indirect Incomes', N'Liabilities'),
 (N'Individual Client', N'Assets'),
 (N'Investments', N'Assets'),
 (N'Loans & Advances (Asset)', N'Assets'),
 (N'Loans (Liability)', N'Liabilities'),
 (N'Misc. Expenses (ASSET)', N'Assets'),
 (N'Provisions', N'Liabilities'),
 (N'Purchase Accounts', N'Assets'),
 (N'Rent Income', N'Liabilities'),
 (N'Reserves & Surplus', N'Liabilities'),
 (N'Retained Earnings', N'Liabilities'),
 (N'Salary and Wages', N'Assets'),
 (N'Sales Accounts', N'Liabilities'),
 (N'Secured Loans', N'Liabilities'),
 (N'Stock Holding Corporation of India', N'Assets'),
 (N'Stock-in-Hand', N'Assets'),
 (N'Sundry Creditors', N'Liabilities'),
 (N'Sundry Debtors', N'Assets'),
 (N'Suspense A/c', N'Assets'),
 (N'Unsecured Loans', N'Liabilities');

INSERT INTO dbo.ChartOfGroupMaster (GroupName, UnderType, IsActive)
SELECT s.GroupName, s.UnderType, 1
FROM @Seed s
WHERE NOT EXISTS (
    SELECT 1 FROM dbo.ChartOfGroupMaster g WHERE g.GroupName = s.GroupName
);
GO

PRINT '086_chart_group_account_masters.sql completed.';
GO
