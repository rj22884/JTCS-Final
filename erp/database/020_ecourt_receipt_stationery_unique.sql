/*
    e-Court Activity — prevent duplicate ReceiptNo + StationeryNumber across all imports
*/
USE JTCSS;
GO

IF COL_LENGTH(N'dbo.ECourtReceiptLine', N'StationeryNumber') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_ECourtReceiptLine_ReceiptStationery')
BEGIN
    CREATE UNIQUE INDEX UX_ECourtReceiptLine_ReceiptStationery
        ON dbo.ECourtReceiptLine (ReceiptNo, StationeryNumber)
        WHERE StationeryNumber IS NOT NULL;
END;
GO

PRINT '020_ecourt_receipt_stationery_unique.sql completed.';
GO
