/*
    Customer Master — Fixed Asset depreciation + Investment appreciation
    Same extra fields as Item Master: PurchaseDate, DepreciationRate, AppreciationRate.
*/
SET NOCOUNT ON;

IF OBJECT_ID(N'dbo.CustomerMaster', N'U') IS NOT NULL
BEGIN
    IF COL_LENGTH(N'dbo.CustomerMaster', N'PurchaseDate') IS NULL
        ALTER TABLE dbo.CustomerMaster ADD PurchaseDate DATE NULL;

    IF COL_LENGTH(N'dbo.CustomerMaster', N'DepreciationRate') IS NULL
        ALTER TABLE dbo.CustomerMaster ADD DepreciationRate DECIMAL(9, 4) NOT NULL
            CONSTRAINT DF_CustomerMaster_DepreciationRate DEFAULT (0);

    IF COL_LENGTH(N'dbo.CustomerMaster', N'AppreciationRate') IS NULL
        ALTER TABLE dbo.CustomerMaster ADD AppreciationRate DECIMAL(9, 4) NOT NULL
            CONSTRAINT DF_CustomerMaster_AppreciationRate DEFAULT (0);
END
GO
