/*
    Dynamic Master Fields — extra columns on Work / Bank masters.
    Trigger is Chart of Account Group only (Fixed Assets / Investments).
    Defaults keep existing rows and existing postings unchanged.
*/
SET NOCOUNT ON;

IF OBJECT_ID(N'dbo.WorkMaster', N'U') IS NOT NULL
BEGIN
    IF COL_LENGTH(N'dbo.WorkMaster', N'PurchaseDate') IS NULL
        ALTER TABLE dbo.WorkMaster ADD PurchaseDate DATE NULL;

    IF COL_LENGTH(N'dbo.WorkMaster', N'DepreciationRate') IS NULL
        ALTER TABLE dbo.WorkMaster ADD DepreciationRate DECIMAL(9, 4) NOT NULL
            CONSTRAINT DF_WorkMaster_DepreciationRate DEFAULT (0);

    IF COL_LENGTH(N'dbo.WorkMaster', N'AppreciationRate') IS NULL
        ALTER TABLE dbo.WorkMaster ADD AppreciationRate DECIMAL(9, 4) NOT NULL
            CONSTRAINT DF_WorkMaster_AppreciationRate DEFAULT (0);
END
GO

IF OBJECT_ID(N'dbo.JtcsBankAccountMaster', N'U') IS NOT NULL
BEGIN
    IF COL_LENGTH(N'dbo.JtcsBankAccountMaster', N'PurchaseDate') IS NULL
        ALTER TABLE dbo.JtcsBankAccountMaster ADD PurchaseDate DATE NULL;

    IF COL_LENGTH(N'dbo.JtcsBankAccountMaster', N'DepreciationRate') IS NULL
        ALTER TABLE dbo.JtcsBankAccountMaster ADD DepreciationRate DECIMAL(9, 4) NOT NULL
            CONSTRAINT DF_Bank_DepreciationRate DEFAULT (0);

    IF COL_LENGTH(N'dbo.JtcsBankAccountMaster', N'AppreciationRate') IS NULL
        ALTER TABLE dbo.JtcsBankAccountMaster ADD AppreciationRate DECIMAL(9, 4) NOT NULL
            CONSTRAINT DF_Bank_AppreciationRate DEFAULT (0);
END
GO
