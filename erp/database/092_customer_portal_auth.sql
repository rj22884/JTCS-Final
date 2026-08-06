-- Customer Portal authentication columns on CustomerMaster + login audit log.
-- Idempotent: safe to re-run.

IF COL_LENGTH(N'dbo.CustomerMaster', N'PortalPassword') IS NULL
    ALTER TABLE dbo.CustomerMaster ADD PortalPassword NVARCHAR(255) NULL;
GO

IF COL_LENGTH(N'dbo.CustomerMaster', N'PasswordChanged') IS NULL
    ALTER TABLE dbo.CustomerMaster ADD PasswordChanged BIT NOT NULL
        CONSTRAINT DF_CustomerMaster_PasswordChanged DEFAULT (0);
GO

IF COL_LENGTH(N'dbo.CustomerMaster', N'LastLogin') IS NULL
    ALTER TABLE dbo.CustomerMaster ADD LastLogin DATETIME2 NULL;
GO

IF COL_LENGTH(N'dbo.CustomerMaster', N'LastPasswordChange') IS NULL
    ALTER TABLE dbo.CustomerMaster ADD LastPasswordChange DATETIME2 NULL;
GO

IF COL_LENGTH(N'dbo.CustomerMaster', N'PasswordResetDate') IS NULL
    ALTER TABLE dbo.CustomerMaster ADD PasswordResetDate DATETIME2 NULL;
GO

IF COL_LENGTH(N'dbo.CustomerMaster', N'FailedLoginCount') IS NULL
    ALTER TABLE dbo.CustomerMaster ADD FailedLoginCount INT NOT NULL
        CONSTRAINT DF_CustomerMaster_FailedLoginCount DEFAULT (0);
GO

IF COL_LENGTH(N'dbo.CustomerMaster', N'AccountLocked') IS NULL
    ALTER TABLE dbo.CustomerMaster ADD AccountLocked BIT NOT NULL
        CONSTRAINT DF_CustomerMaster_AccountLocked DEFAULT (0);
GO

IF OBJECT_ID(N'dbo.CustomerPortalLoginLog', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.CustomerPortalLoginLog (
        LogID           BIGINT IDENTITY(1, 1) NOT NULL,
        CustomerID      INT NULL,
        UserIdInput     NVARCHAR(255) NOT NULL,
        DetectedType    NVARCHAR(20) NULL,
        AttemptResult   NVARCHAR(40) NOT NULL,
        IpAddress       NVARCHAR(64) NULL,
        UserAgent       NVARCHAR(500) NULL,
        CreatedDate     DATETIME2 NOT NULL CONSTRAINT DF_CustomerPortalLoginLog_CreatedDate DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT PK_CustomerPortalLoginLog PRIMARY KEY (LogID)
    );
    CREATE INDEX IX_CustomerPortalLoginLog_CustomerID
        ON dbo.CustomerPortalLoginLog (CustomerID);
    CREATE INDEX IX_CustomerPortalLoginLog_CreatedDate
        ON dbo.CustomerPortalLoginLog (CreatedDate);
END
GO
