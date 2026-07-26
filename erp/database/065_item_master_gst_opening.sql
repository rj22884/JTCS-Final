-- Item Master: GST Applicable + Opening Qty/Rate/Balance/Date
IF COL_LENGTH(N'dbo.ItemMaster', N'GstApplicable') IS NULL
    ALTER TABLE dbo.ItemMaster ADD GstApplicable BIT NOT NULL
        CONSTRAINT DF_ItemMaster_GstApplicable DEFAULT (1);
GO
IF COL_LENGTH(N'dbo.ItemMaster', N'OpeningQty') IS NULL
    ALTER TABLE dbo.ItemMaster ADD OpeningQty DECIMAL(18, 3) NOT NULL
        CONSTRAINT DF_ItemMaster_OpeningQty DEFAULT (0);
GO
IF COL_LENGTH(N'dbo.ItemMaster', N'OpeningRate') IS NULL
    ALTER TABLE dbo.ItemMaster ADD OpeningRate DECIMAL(18, 2) NOT NULL
        CONSTRAINT DF_ItemMaster_OpeningRate DEFAULT (0);
GO
IF COL_LENGTH(N'dbo.ItemMaster', N'OpeningBalance') IS NULL
    ALTER TABLE dbo.ItemMaster ADD OpeningBalance DECIMAL(18, 2) NOT NULL
        CONSTRAINT DF_ItemMaster_OpeningBalance DEFAULT (0);
GO
IF COL_LENGTH(N'dbo.ItemMaster', N'OpeningBalanceDate') IS NULL
    ALTER TABLE dbo.ItemMaster ADD OpeningBalanceDate DATE NULL;
GO
