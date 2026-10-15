/*
    Item Master — Investment appreciation rate
    Same purchase-date field as Fixed Assets; appreciation posts to P&L income
    and increases the Balance Sheet value when rate + dates + opening are set.
*/
SET NOCOUNT ON;

IF OBJECT_ID(N'dbo.ItemMaster', N'U') IS NOT NULL
BEGIN
    IF COL_LENGTH(N'dbo.ItemMaster', N'AppreciationRate') IS NULL
        ALTER TABLE dbo.ItemMaster ADD AppreciationRate DECIMAL(9, 4) NOT NULL
            CONSTRAINT DF_ItemMaster_AppreciationRate DEFAULT (0);
END
GO
