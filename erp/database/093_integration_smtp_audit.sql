/*
  093_integration_smtp_audit.sql
  Ensure AuditLog exists for Integration Settings SMTP updates.
  (Richer schema already used by CRM/ERP — compatible with AuditService.)
*/
SET NOCOUNT ON;
GO

IF OBJECT_ID(N'dbo.AuditLog', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.AuditLog (
        AuditID BIGINT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        UserID INT NULL,
        UserName NVARCHAR(150) NULL,
        ActionName NVARCHAR(100) NOT NULL,
        EntityType NVARCHAR(50) NULL,
        EntityID INT NULL,
        OldValue NVARCHAR(MAX) NULL,
        NewValue NVARCHAR(MAX) NULL,
        IPAddress NVARCHAR(64) NULL,
        Browser NVARCHAR(500) NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_AuditLog_CreatedDate_093 DEFAULT (SYSUTCDATETIME())
    );
    CREATE INDEX IX_AuditLog_Created_093 ON dbo.AuditLog (CreatedDate DESC);
    CREATE INDEX IX_AuditLog_Entity_093 ON dbo.AuditLog (EntityType, EntityID, CreatedDate DESC);
END;
GO

PRINT '093_integration_smtp_audit.sql completed.';
GO
