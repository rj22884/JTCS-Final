/*
    JTCS ERP - Password reset OTP table
*/
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = N'PasswordResetOTP')
BEGIN
    CREATE TABLE dbo.PasswordResetOTP (
        OTPID         INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        UserID        INT NOT NULL,
        Email         NVARCHAR(254) NOT NULL,
        OTP           NVARCHAR(64) NOT NULL,
        Purpose       NVARCHAR(50) NOT NULL CONSTRAINT DF_PasswordResetOTP_Purpose DEFAULT (N'PASSWORD_RESET'),
        CreatedOn     DATETIME2 NOT NULL CONSTRAINT DF_PasswordResetOTP_CreatedOn DEFAULT (SYSUTCDATETIME()),
        ExpiresOn     DATETIME2 NOT NULL,
        Verified      BIT NOT NULL CONSTRAINT DF_PasswordResetOTP_Verified DEFAULT (0),
        AttemptCount  INT NOT NULL CONSTRAINT DF_PasswordResetOTP_AttemptCount DEFAULT (0),
        IsUsed        BIT NOT NULL CONSTRAINT DF_PasswordResetOTP_IsUsed DEFAULT (0),
        CONSTRAINT FK_PasswordResetOTP_User FOREIGN KEY (UserID) REFERENCES dbo.Users (UserID)
    );

    CREATE INDEX IX_PasswordResetOTP_Email ON dbo.PasswordResetOTP (Email, Purpose, IsUsed, Verified);
    CREATE INDEX IX_PasswordResetOTP_Expires ON dbo.PasswordResetOTP (ExpiresOn);
END;
GO
