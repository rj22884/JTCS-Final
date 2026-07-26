/*
    e-Court Activity — receipt import + sale tracking + SHCIL menu
*/
USE JTCSS;
GO

IF OBJECT_ID(N'dbo.ECourtReceiptBatch', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ECourtReceiptBatch (
        ImportID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        FileName NVARCHAR(260) NULL,
        ReportFrom DATE NULL,
        ReportTo DATE NULL,
        StateName NVARCHAR(100) NULL,
        TotalAmount DECIMAL(18, 2) NULL,
        RecordCount INT NULL,
        ImportedBy NVARCHAR(100) NULL,
        ImportedDate DATETIME2 NOT NULL CONSTRAINT DF_ECourtReceiptBatch_ImportedDate DEFAULT (SYSUTCDATETIME())
    );
END;
GO

IF OBJECT_ID(N'dbo.ECourtReceiptLine', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ECourtReceiptLine (
        LineID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        ImportID INT NOT NULL,
        ReceiptNo NVARCHAR(50) NOT NULL,
        ReceiptDate DATE NULL,
        Amount DECIMAL(18, 2) NOT NULL,
        PaymentMode NVARCHAR(50) NULL,
        ReceiptStatus NVARCHAR(100) NULL,
        Remarks NVARCHAR(500) NULL,
        StationeryNo NVARCHAR(20) NULL,
        CONSTRAINT FK_ECourtReceiptLine_Batch FOREIGN KEY (ImportID)
            REFERENCES dbo.ECourtReceiptBatch (ImportID) ON DELETE CASCADE
    );
    CREATE INDEX IX_ECourtReceiptLine_Stationery ON dbo.ECourtReceiptLine (StationeryNo, ImportID);
    CREATE UNIQUE INDEX UX_ECourtReceiptLine_ImportReceipt ON dbo.ECourtReceiptLine (ImportID, ReceiptNo);
END;
GO

IF OBJECT_ID(N'dbo.ECourtSale', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ECourtSale (
        SaleID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        ReceiptNo NVARCHAR(50) NOT NULL,
        StationeryNo NVARCHAR(20) NULL,
        ReceiptDate DATE NULL,
        Amount DECIMAL(18, 2) NOT NULL,
        CustomerName NVARCHAR(255) NULL,
        MobileNumber NVARCHAR(15) NULL,
        Remarks NVARCHAR(500) NULL,
        CreatedBy NVARCHAR(100) NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_ECourtSale_CreatedDate DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT UX_ECourtSale_ReceiptNo UNIQUE (ReceiptNo)
    );
    CREATE INDEX IX_ECourtSale_Stationery ON dbo.ECourtSale (StationeryNo);
END;
GO

DECLARE @ShcilID INT = (SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'SHCIL' AND ParentMenuID IS NULL);

IF @ShcilID IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM dbo.MenuMaster WHERE MenuName = N'e-Court Activity' AND ParentMenuID = @ShcilID)
BEGIN
    INSERT INTO dbo.MenuMaster (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
    VALUES (
        @ShcilID,
        N'e-Court Activity',
        N'bi-file-earmark-text',
        N'/shcil/ecourt-activity',
        2,
        N'SHCIL e-Court fee receipt import and stationery sale check',
        1,
        NULL
    );
END
ELSE IF @ShcilID IS NOT NULL
BEGIN
    UPDATE dbo.MenuMaster
    SET MenuURL = N'/shcil/ecourt-activity',
        MenuIcon = N'bi-file-earmark-text',
        DisplayOrder = 2,
        Description = N'SHCIL e-Court fee receipt import and stationery sale check',
        IsActive = 1
    WHERE MenuName = N'e-Court Activity' AND ParentMenuID = @ShcilID;
END;
GO

PRINT '018_ecourt_activity.sql completed.';
GO
