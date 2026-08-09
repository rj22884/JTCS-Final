/*
  094_user_login_activity.sql
  Staff login activity + password event tracking for Admin Dashboard.
  Idempotent: safe to re-run.
*/
SET NOCOUNT ON;
GO

/* Users.IsPasswordSet — 0 until first real password is chosen via emailed link */
IF COL_LENGTH(N'dbo.Users', N'IsPasswordSet') IS NULL
BEGIN
    ALTER TABLE dbo.Users ADD IsPasswordSet BIT NOT NULL
        CONSTRAINT DF_Users_IsPasswordSet DEFAULT (0);
END;
GO

/* Existing accounts that already log in: treat password as set */
UPDATE dbo.Users
SET IsPasswordSet = 1
WHERE IsPasswordSet = 0
  AND (
        EmailVerified = 1
        OR UserStatus = N'Active'
        OR Role LIKE N'%Administrator%'
        OR Role LIKE N'%Admin%'
      );
GO

IF OBJECT_ID(N'dbo.user_login_activity', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.user_login_activity (
        id INT IDENTITY(1, 1) NOT NULL CONSTRAINT PK_user_login_activity PRIMARY KEY,
        user_id NVARCHAR(100) NOT NULL,
        user_pk INT NULL,
        login_time DATETIME NOT NULL CONSTRAINT DF_user_login_activity_login_time DEFAULT (GETDATE()),
        ip_address NVARCHAR(50) NULL,
        device NVARCHAR(300) NULL,
        status NVARCHAR(20) NOT NULL,
        session_id NVARCHAR(200) NULL,
        logout_time DATETIME NULL
    );
    CREATE INDEX IX_user_login_activity_login_time
        ON dbo.user_login_activity (login_time DESC);
    CREATE INDEX IX_user_login_activity_user_id
        ON dbo.user_login_activity (user_id, login_time DESC);
    CREATE INDEX IX_user_login_activity_session_id
        ON dbo.user_login_activity (session_id)
        WHERE session_id IS NOT NULL;
END;
GO

IF OBJECT_ID(N'dbo.user_password_events', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.user_password_events (
        id INT IDENTITY(1, 1) NOT NULL CONSTRAINT PK_user_password_events PRIMARY KEY,
        user_id NVARCHAR(100) NOT NULL,
        user_pk INT NULL,
        event_type NVARCHAR(50) NOT NULL,
        event_time DATETIME NOT NULL CONSTRAINT DF_user_password_events_event_time DEFAULT (GETDATE())
    );
    CREATE INDEX IX_user_password_events_event_time
        ON dbo.user_password_events (event_time DESC);
    CREATE INDEX IX_user_password_events_user_id
        ON dbo.user_password_events (user_id, event_time DESC);
END;
GO

PRINT '094_user_login_activity.sql completed.';
GO
