/*
    Universal notifications + audit log
*/
USE JTCSS;
GO

IF OBJECT_ID(N'dbo.Notification', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Notification (
        NotificationID BIGINT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        UserID INT NULL,
        NotificationType NVARCHAR(50) NOT NULL,
        Title NVARCHAR(255) NOT NULL,
        Message NVARCHAR(MAX) NULL,
        LinkURL NVARCHAR(500) NULL,
        Priority NVARCHAR(20) NOT NULL CONSTRAINT DF_Notification_Priority DEFAULT (N'Normal'),
        IsRead BIT NOT NULL CONSTRAINT DF_Notification_IsRead DEFAULT (0),
        IsArchived BIT NOT NULL CONSTRAINT DF_Notification_IsArchived DEFAULT (0),
        CustomerID INT NULL,
        LeadID INT NULL,
        EntityType NVARCHAR(50) NULL,
        EntityID INT NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_Notification_CreatedDate DEFAULT (SYSUTCDATETIME()),
        ReadDate DATETIME2 NULL
    );
    CREATE INDEX IX_Notification_UserUnread ON dbo.Notification (UserID, IsRead, IsArchived, CreatedDate DESC);
    CREATE INDEX IX_Notification_Type ON dbo.Notification (NotificationType, CreatedDate DESC);
END;
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
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_AuditLog_CreatedDate DEFAULT (SYSUTCDATETIME())
    );
    CREATE INDEX IX_AuditLog_Created ON dbo.AuditLog (CreatedDate DESC);
    CREATE INDEX IX_AuditLog_Entity ON dbo.AuditLog (EntityType, EntityID, CreatedDate DESC);
END;
GO

PRINT '070_notifications_audit.sql completed.';
GO
