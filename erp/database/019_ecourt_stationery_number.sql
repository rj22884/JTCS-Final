/*
    Rename StationeryNo -> StationeryNumber on e-Court tables
*/
USE JTCSS;
GO

IF COL_LENGTH(N'dbo.ECourtReceiptLine', N'StationeryNo') IS NOT NULL
   AND COL_LENGTH(N'dbo.ECourtReceiptLine', N'StationeryNumber') IS NULL
    EXEC sp_rename N'dbo.ECourtReceiptLine.StationeryNo', N'StationeryNumber', N'COLUMN';
GO

IF COL_LENGTH(N'dbo.ECourtSale', N'StationeryNo') IS NOT NULL
   AND COL_LENGTH(N'dbo.ECourtSale', N'StationeryNumber') IS NULL
    EXEC sp_rename N'dbo.ECourtSale.StationeryNo', N'StationeryNumber', N'COLUMN';
GO

IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_ECourtReceiptLine_Stationery')
BEGIN
    DROP INDEX IX_ECourtReceiptLine_Stationery ON dbo.ECourtReceiptLine;
END;
GO

IF COL_LENGTH(N'dbo.ECourtReceiptLine', N'StationeryNumber') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_ECourtReceiptLine_StationeryNumber')
    CREATE INDEX IX_ECourtReceiptLine_StationeryNumber ON dbo.ECourtReceiptLine (StationeryNumber, ImportID);
GO

IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_ECourtSale_Stationery')
BEGIN
    DROP INDEX IX_ECourtSale_Stationery ON dbo.ECourtSale;
END;
GO

IF COL_LENGTH(N'dbo.ECourtSale', N'StationeryNumber') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_ECourtSale_StationeryNumber')
    CREATE INDEX IX_ECourtSale_StationeryNumber ON dbo.ECourtSale (StationeryNumber);
GO

PRINT '019_ecourt_stationery_number.sql completed.';
GO
