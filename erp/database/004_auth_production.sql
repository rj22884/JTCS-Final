/*
    JTCS ERP - Production authentication tables and Users extensions
*/

IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID(N'dbo.Users') AND name = N'Department')
    ALTER TABLE dbo.Users ADD Department NVARCHAR(100) NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID(N'dbo.Users') AND name = N'Designation')
    ALTER TABLE dbo.Users ADD Designation NVARCHAR(100) NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID(N'dbo.Users') AND name = N'UserStatus')
    ALTER TABLE dbo.Users ADD UserStatus NVARCHAR(50) NOT NULL CONSTRAINT DF_Users_UserStatus DEFAULT (N'Active');
GO

IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID(N'dbo.Users') AND name = N'EmailVerified')
    ALTER TABLE dbo.Users ADD EmailVerified BIT NOT NULL CONSTRAINT DF_Users_EmailVerified DEFAULT (0);
GO

IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID(N'dbo.Users') AND name = N'AdminApproved')
    ALTER TABLE dbo.Users ADD AdminApproved BIT NOT NULL CONSTRAINT DF_Users_AdminApproved DEFAULT (0);
GO

UPDATE dbo.Users
SET UserStatus = N'Active',
    EmailVerified = 1,
    AdminApproved = 1
WHERE Role = N'Administrator' AND IsActive = 1;
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = N'CompanyProfile')
BEGIN
    CREATE TABLE dbo.CompanyProfile (
        CompanyID       INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        CompanyName     NVARCHAR(200) NOT NULL,
        OwnerName       NVARCHAR(200) NOT NULL,
        LogoPath        NVARCHAR(500) NULL,
        SetupCompleted  BIT NOT NULL CONSTRAINT DF_CompanyProfile_SetupCompleted DEFAULT (0),
        CreatedDate     DATETIME2 NOT NULL CONSTRAINT DF_CompanyProfile_CreatedDate DEFAULT (SYSUTCDATETIME()),
        ModifiedDate    DATETIME2 NULL
    );
END;
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = N'AuthToken')
BEGIN
    CREATE TABLE dbo.AuthToken (
        AuthTokenID     INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        UserID          INT NULL,
        Email           NVARCHAR(254) NULL,
        MobileNumber    NVARCHAR(15) NULL,
        TokenType       NVARCHAR(50) NOT NULL,
        TokenHash       NVARCHAR(255) NOT NULL,
        ExpiresAt       DATETIME2 NOT NULL,
        IsUsed          BIT NOT NULL CONSTRAINT DF_AuthToken_IsUsed DEFAULT (0),
        CreatedDate     DATETIME2 NOT NULL CONSTRAINT DF_AuthToken_CreatedDate DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT FK_AuthToken_User FOREIGN KEY (UserID) REFERENCES dbo.Users (UserID)
    );

    CREATE INDEX IX_AuthToken_Email ON dbo.AuthToken (Email, TokenType, IsUsed);
    CREATE INDEX IX_AuthToken_Mobile ON dbo.AuthToken (MobileNumber, TokenType, IsUsed);
    CREATE INDEX IX_AuthToken_Expires ON dbo.AuthToken (ExpiresAt);
END;
GO

IF EXISTS (SELECT 1 FROM dbo.Users WHERE Role = N'Administrator' AND IsActive = 1)
   AND NOT EXISTS (SELECT 1 FROM dbo.CompanyProfile)
BEGIN
    INSERT INTO dbo.CompanyProfile (CompanyName, OwnerName, SetupCompleted)
    VALUES (N'JTCS', N'System Owner', 1);
END;
GO
