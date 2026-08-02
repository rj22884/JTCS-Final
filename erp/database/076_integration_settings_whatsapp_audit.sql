/*
    Integration Settings audit log (WhatsApp / integrations credential changes)
*/
USE JTCSS;
GO

IF OBJECT_ID(N'dbo.IntegrationSettingsAudit', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.IntegrationSettingsAudit (
        AuditID BIGINT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        Provider NVARCHAR(50) NOT NULL,
        SettingKey NVARCHAR(100) NOT NULL,
        OldValueMasked NVARCHAR(MAX) NULL,
        NewValueMasked NVARCHAR(MAX) NULL,
        ChangedByUserID INT NULL,
        ChangedByUserName NVARCHAR(150) NULL,
        IPAddress NVARCHAR(64) NULL,
        Browser NVARCHAR(500) NULL,
        CreatedOn DATETIME2 NOT NULL CONSTRAINT DF_IntegrationSettingsAudit_CreatedOn DEFAULT (SYSUTCDATETIME())
    );
    CREATE INDEX IX_IntegrationSettingsAudit_Provider
        ON dbo.IntegrationSettingsAudit (Provider, CreatedOn DESC);
END;
GO

PRINT '076_integration_settings_whatsapp_audit.sql completed.';
GO
