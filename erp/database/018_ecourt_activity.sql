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

/* eCourt Activity belongs under Activities (same as local Menu Admin layout) */
DECLARE @ActivitiesID INT = (
    SELECT TOP 1 MenuID
    FROM dbo.MenuMaster
    WHERE MenuName = N'Activities' AND ParentMenuID IS NULL
    ORDER BY MenuID
);

IF @ActivitiesID IS NULL
BEGIN
    INSERT INTO dbo.MenuMaster (MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
    VALUES (N'Activities', N'bi-lightning-charge', NULL, 2, N'Daily operational activities', 1, NULL);
    SET @ActivitiesID = SCOPE_IDENTITY();
END;

DECLARE @EcourtID INT = (
    SELECT TOP 1 MenuID
    FROM dbo.MenuMaster
    WHERE MenuURL = N'/shcil/ecourt-activity'
       OR MenuName IN (N'eCourt Activity', N'e-Court Activity')
    ORDER BY CASE WHEN MenuURL = N'/shcil/ecourt-activity' THEN 0 ELSE 1 END, MenuID
);

IF @EcourtID IS NULL
BEGIN
    INSERT INTO dbo.MenuMaster (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
    VALUES (
        @ActivitiesID,
        N'eCourt Activity',
        N'bi-file-earmark-text',
        N'/shcil/ecourt-activity',
        1,
        N'SHCIL e-Court fee receipt import and stationery sale check',
        1,
        NULL
    );
END
ELSE
BEGIN
    UPDATE dbo.MenuMaster
    SET ParentMenuID = @ActivitiesID,
        MenuName = CASE
            WHEN MenuName IN (N'eCourt Activity', N'e-Court Activity') THEN MenuName
            ELSE N'eCourt Activity'
        END,
        MenuURL = N'/shcil/ecourt-activity',
        MenuIcon = N'bi-file-earmark-text',
        DisplayOrder = CASE WHEN ParentMenuID = @ActivitiesID THEN DisplayOrder ELSE 1 END,
        Description = N'SHCIL e-Court fee receipt import and stationery sale check',
        IsActive = 1
    WHERE MenuID = @EcourtID;
END;

/* Hide empty top-level SHCIL after children moved to Activities */
UPDATE dbo.MenuMaster
SET IsActive = 0
WHERE MenuName = N'SHCIL'
  AND ParentMenuID IS NULL
  AND NOT EXISTS (
        SELECT 1
        FROM dbo.MenuMaster c
        WHERE c.ParentMenuID = MenuMaster.MenuID
          AND c.IsActive = 1
  );
GO

PRINT '018_ecourt_activity.sql completed.';
GO
