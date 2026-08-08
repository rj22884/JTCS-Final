/*
  Integration Health — history + alerts.
  Does NOT duplicate IntegrationSettings (config remains in existing tables).
*/

IF OBJECT_ID(N'dbo.IntegrationHealthCheck', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.IntegrationHealthCheck (
        HealthCheckID BIGINT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        Provider NVARCHAR(50) NOT NULL,
        StatusCode NVARCHAR(40) NOT NULL,
        HealthScore INT NOT NULL CONSTRAINT DF_IHC_Score DEFAULT (0),
        StatusLabel NVARCHAR(80) NULL,
        TokenStatus NVARCHAR(40) NULL,
        WebhookStatus NVARCHAR(40) NULL,
        ApiVersion NVARCHAR(40) NULL,
        AvgResponseMs INT NULL,
        LastError NVARCHAR(1000) NULL,
        DetailsJson NVARCHAR(MAX) NULL,
        CheckedOn DATETIME2 NOT NULL CONSTRAINT DF_IHC_CheckedOn DEFAULT (SYSUTCDATETIME()),
        CheckedByUserID INT NULL
    );
    CREATE INDEX IX_IHC_Provider ON dbo.IntegrationHealthCheck (Provider, CheckedOn DESC);
END;
GO

IF OBJECT_ID(N'dbo.IntegrationHealthAlert', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.IntegrationHealthAlert (
        AlertID BIGINT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        Provider NVARCHAR(50) NOT NULL,
        AlertType NVARCHAR(60) NOT NULL,
        Severity NVARCHAR(20) NOT NULL CONSTRAINT DF_IHA_Severity DEFAULT (N'Warning'),
        Title NVARCHAR(255) NOT NULL,
        Message NVARCHAR(1000) NULL,
        IsResolved BIT NOT NULL CONSTRAINT DF_IHA_Resolved DEFAULT (0),
        CreatedOn DATETIME2 NOT NULL CONSTRAINT DF_IHA_CreatedOn DEFAULT (SYSUTCDATETIME()),
        ResolvedOn DATETIME2 NULL
    );
    CREATE INDEX IX_IHA_Open ON dbo.IntegrationHealthAlert (IsResolved, CreatedOn DESC);
END;
GO
