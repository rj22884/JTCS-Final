/*
    e-Court Activity — unique receipt number only (not receipt + stationery)
*/
USE JTCSS;
GO

IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_ECourtReceiptLine_ReceiptStationery')
    DROP INDEX UX_ECourtReceiptLine_ReceiptStationery ON dbo.ECourtReceiptLine;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_ECourtReceiptLine_ReceiptNo')
    CREATE UNIQUE INDEX UX_ECourtReceiptLine_ReceiptNo ON dbo.ECourtReceiptLine (ReceiptNo);
GO

PRINT '022_ecourt_receipt_no_unique.sql completed.';
GO
