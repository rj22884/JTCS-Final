/*
    Server User authentication (second factor after JTCS Users login)
    + AuditLog Module / Status columns for the activity trail.
    Does not alter dbo.Users rows or financial data.
*/
USE JTCSS;
GO

IF OBJECT_ID(N'dbo.ServerUser', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ServerUser (
        ServerUserID INT IDENTITY(1, 1) NOT NULL
            CONSTRAINT PK_ServerUser PRIMARY KEY,
        UserID INT NOT NULL,
        LoginID NVARCHAR(80) NOT NULL,
        PasswordHash NVARCHAR(255) NOT NULL,
        IsActive BIT NOT NULL CONSTRAINT DF_ServerUser_IsActive DEFAULT (1),
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_ServerUser_CreatedDate DEFAULT (SYSUTCDATETIME()),
        ModifiedDate DATETIME2 NULL,
        LastLoginDate DATETIME2 NULL,
        CONSTRAINT UQ_ServerUser_UserID UNIQUE (UserID),
        CONSTRAINT UQ_ServerUser_LoginID UNIQUE (LoginID),
        CONSTRAINT FK_ServerUser_Users FOREIGN KEY (UserID) REFERENCES dbo.Users (UserID)
    );
    CREATE INDEX IX_ServerUser_LoginID ON dbo.ServerUser (LoginID);
END;
GO

IF COL_LENGTH(N'dbo.AuditLog', N'Module') IS NULL
    ALTER TABLE dbo.AuditLog ADD Module NVARCHAR(100) NULL;
GO

IF COL_LENGTH(N'dbo.AuditLog', N'Status') IS NULL
    ALTER TABLE dbo.AuditLog ADD Status NVARCHAR(30) NULL;
GO

PRINT '101_server_user_auth.sql completed.';
GO
