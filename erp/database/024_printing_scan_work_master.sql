/*
    Others — shared WorkMaster (Income / Expense heads) + Printing & Scanning
*/
USE JTCSS;
GO

IF OBJECT_ID(N'dbo.WorkMaster', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.WorkMaster (
        WorkID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        WorkName NVARCHAR(100) NOT NULL,
        LedgerKind NVARCHAR(10) NOT NULL,
        ActiveStatus BIT NOT NULL CONSTRAINT DF_WorkMaster_ActiveStatus DEFAULT (1),
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_WorkMaster_CreatedDate DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT CK_WorkMaster_LedgerKind CHECK (LedgerKind IN (N'Income', N'Expense')),
        CONSTRAINT UX_WorkMaster_NameKind UNIQUE (WorkName, LedgerKind)
    );
    CREATE INDEX IX_WorkMaster_LedgerKind ON dbo.WorkMaster (LedgerKind, ActiveStatus);
END;
GO

IF OBJECT_ID(N'dbo.PrintingScanMaster', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.PrintingScanMaster (
        PrintingScanID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        BillNo NVARCHAR(50) NOT NULL,
        WorkDate DATE NOT NULL,
        WorkID INT NOT NULL,
        SaleAmount DECIMAL(18, 2) NOT NULL,
        CustomerName NVARCHAR(255) NULL,
        MobileNumber NVARCHAR(15) NULL,
        Remarks NVARCHAR(500) NULL,
        CreatedBy NVARCHAR(100) NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_PrintingScanMaster_CreatedDate DEFAULT (SYSUTCDATETIME()),
        IsActive BIT NOT NULL CONSTRAINT DF_PrintingScanMaster_IsActive DEFAULT (1),
        CONSTRAINT FK_PrintingScanMaster_Work FOREIGN KEY (WorkID) REFERENCES dbo.WorkMaster (WorkID),
        CONSTRAINT UX_PrintingScanMaster_BillNo UNIQUE (BillNo)
    );
    CREATE INDEX IX_PrintingScanMaster_WorkDate ON dbo.PrintingScanMaster (WorkDate, WorkID);
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM dbo.WorkMaster
    WHERE WorkName = N'Photostat' AND LedgerKind = N'Income'
)
    INSERT INTO dbo.WorkMaster (WorkName, LedgerKind) VALUES (N'Photostat', N'Income');

IF NOT EXISTS (
    SELECT 1 FROM dbo.WorkMaster
    WHERE WorkName = N'Print & Scan' AND LedgerKind = N'Income'
)
    INSERT INTO dbo.WorkMaster (WorkName, LedgerKind) VALUES (N'Print & Scan', N'Income');
GO

PRINT '024_printing_scan_work_master.sql completed.';
GO
