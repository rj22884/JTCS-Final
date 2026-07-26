/*
    Dashboard popup manual entries (card drill-down Add/Edit/Delete)
*/
USE JTCSS;
GO

IF OBJECT_ID(N'dbo.DashboardManualEntry', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.DashboardManualEntry (
        EntryID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        MetricKey NVARCHAR(50) NOT NULL,
        EntryDate DATE NOT NULL,
        Description NVARCHAR(500) NULL,
        Amount DECIMAL(18, 2) NOT NULL,
        CreatedBy NVARCHAR(150) NULL,
        CreatedDate DATETIME2 NOT NULL
            CONSTRAINT DF_DashboardManualEntry_CreatedDate DEFAULT (SYSUTCDATETIME()),
        ModifiedDate DATETIME2 NULL,
        IsActive BIT NOT NULL
            CONSTRAINT DF_DashboardManualEntry_IsActive DEFAULT (1)
    );
    CREATE INDEX IX_DashboardManualEntry_Metric_Date
        ON dbo.DashboardManualEntry (MetricKey, EntryDate, IsActive);
END;
GO

PRINT '046_dashboard_manual_entry.sql completed.';
GO
