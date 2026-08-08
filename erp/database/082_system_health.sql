/*
  System Health Mission Control — scans, alerts, metric samples.
  Does not duplicate IntegrationSettings or Backup inventory tables.
*/

IF OBJECT_ID(N'dbo.SystemHealthScan', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.SystemHealthScan (
        ScanID BIGINT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        OverallScore INT NOT NULL CONSTRAINT DF_SHS_Score DEFAULT (0),
        StatusLabel NVARCHAR(40) NULL,
        SummaryJson NVARCHAR(MAX) NULL,
        DetailsJson NVARCHAR(MAX) NULL,
        ScannedOn DATETIME2 NOT NULL CONSTRAINT DF_SHS_On DEFAULT (SYSUTCDATETIME()),
        ScannedByUserID INT NULL
    );
    CREATE INDEX IX_SHS_ScannedOn ON dbo.SystemHealthScan (ScannedOn DESC);
END;
GO

IF OBJECT_ID(N'dbo.SystemHealthAlert', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.SystemHealthAlert (
        AlertID BIGINT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        AlertType NVARCHAR(60) NOT NULL,
        Severity NVARCHAR(20) NOT NULL CONSTRAINT DF_SHA_Sev DEFAULT (N'Warning'),
        Title NVARCHAR(255) NOT NULL,
        Message NVARCHAR(1000) NULL,
        IsResolved BIT NOT NULL CONSTRAINT DF_SHA_Res DEFAULT (0),
        CreatedOn DATETIME2 NOT NULL CONSTRAINT DF_SHA_On DEFAULT (SYSUTCDATETIME()),
        ResolvedOn DATETIME2 NULL
    );
    CREATE INDEX IX_SHA_Open ON dbo.SystemHealthAlert (IsResolved, CreatedOn DESC);
END;
GO

IF OBJECT_ID(N'dbo.SystemHealthMetric', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.SystemHealthMetric (
        MetricID BIGINT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        MetricKey NVARCHAR(40) NOT NULL,
        MetricValue FLOAT NOT NULL,
        SampledOn DATETIME2 NOT NULL CONSTRAINT DF_SHM_On DEFAULT (SYSUTCDATETIME())
    );
    CREATE INDEX IX_SHM_KeyOn ON dbo.SystemHealthMetric (MetricKey, SampledOn DESC);
END;
GO
