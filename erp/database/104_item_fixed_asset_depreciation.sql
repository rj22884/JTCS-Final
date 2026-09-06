/*
    Item Master — Fixed Asset purchase date + depreciation rate
    FixedAssetMaster.ItemID links auto-synced assets from Item Master.
*/
SET NOCOUNT ON;

IF OBJECT_ID(N'dbo.ItemMaster', N'U') IS NOT NULL
BEGIN
    IF COL_LENGTH(N'dbo.ItemMaster', N'PurchaseDate') IS NULL
        ALTER TABLE dbo.ItemMaster ADD PurchaseDate DATE NULL;

    IF COL_LENGTH(N'dbo.ItemMaster', N'DepreciationRate') IS NULL
        ALTER TABLE dbo.ItemMaster ADD DepreciationRate DECIMAL(9, 4) NOT NULL
            CONSTRAINT DF_ItemMaster_DepreciationRate DEFAULT (0);
END
GO

IF OBJECT_ID(N'dbo.FixedAssetMaster', N'U') IS NOT NULL
BEGIN
    IF COL_LENGTH(N'dbo.FixedAssetMaster', N'ItemID') IS NULL
        ALTER TABLE dbo.FixedAssetMaster ADD ItemID INT NULL;

    IF COL_LENGTH(N'dbo.FixedAssetMaster', N'ItemID') IS NOT NULL
       AND NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = N'UX_FixedAssetMaster_ItemID'
              AND object_id = OBJECT_ID(N'dbo.FixedAssetMaster')
       )
        CREATE UNIQUE INDEX UX_FixedAssetMaster_ItemID
            ON dbo.FixedAssetMaster (ItemID)
            WHERE ItemID IS NOT NULL;
END
GO
