/*
  JTCS ERP — Application version history + change log + menu
  Idempotent. Apply via sqlcmd / deployment/apply_migrations.sh
*/

USE JTCSS;
GO

SET NOCOUNT ON;

IF OBJECT_ID(N'dbo.AppVersionHistory', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.AppVersionHistory (
        VersionID               INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        ApplicationVersion      NVARCHAR(20)  NOT NULL,
        BuildNumber             INT           NOT NULL CONSTRAINT DF_AppVersion_Build DEFAULT (1),
        DatabaseVersion         NVARCHAR(20)  NULL,
        GitCommitID             NVARCHAR(64)  NULL,
        GitBranch               NVARCHAR(100) NULL,
        DeveloperName           NVARCHAR(100) NULL,
        ReleaseNotes            NVARCHAR(MAX) NULL,
        WhatsNew                NVARCHAR(MAX) NULL,
        BugFixes                NVARCHAR(MAX) NULL,
        NewFeatures             NVARCHAR(MAX) NULL,
        DatabaseChanges         NVARCHAR(MAX) NULL,
        SecurityUpdates         NVARCHAR(MAX) NULL,
        PerformanceImprovements NVARCHAR(MAX) NULL,
        DeploymentStatus        NVARCHAR(30)  NOT NULL CONSTRAINT DF_AppVersion_Status DEFAULT (N'Success'),
        BackupPath              NVARCHAR(500) NULL,
        DeployedAt              DATETIME2     NOT NULL CONSTRAINT DF_AppVersion_DeployedAt DEFAULT (SYSUTCDATETIME()),
        IsCurrent               BIT           NOT NULL CONSTRAINT DF_AppVersion_IsCurrent DEFAULT (0),
        CreatedDate             DATETIME2     NOT NULL CONSTRAINT DF_AppVersion_Created DEFAULT (SYSUTCDATETIME())
    );

    CREATE INDEX IX_AppVersionHistory_IsCurrent
        ON dbo.AppVersionHistory (IsCurrent)
        INCLUDE (ApplicationVersion, BuildNumber, DeployedAt);

    CREATE INDEX IX_AppVersionHistory_AppVersion
        ON dbo.AppVersionHistory (ApplicationVersion);
END
GO

/* Seed initial current version if empty */
IF NOT EXISTS (SELECT 1 FROM dbo.AppVersionHistory)
BEGIN
    INSERT INTO dbo.AppVersionHistory (
        ApplicationVersion, BuildNumber, DatabaseVersion,
        ReleaseNotes, DeploymentStatus, IsCurrent
    )
    VALUES (
        N'1.0.0', 1, N'1.0.0',
        N'Initial version baseline', N'Success', 1
    );
END
GO

/* Admin Role → Software Updates menu */
DECLARE @ParentID INT;
DECLARE @AdminRoles NVARCHAR(50) = N'Administrator,Admin';

SELECT TOP 1 @ParentID = MenuID
FROM dbo.MenuMaster
WHERE MenuName = N'Admin Role'
  AND ParentMenuID IS NULL
ORDER BY MenuID;

IF @ParentID IS NULL
BEGIN
    INSERT INTO dbo.MenuMaster (
        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
        Description, IsActive, RoleName
    )
    VALUES (
        NULL, N'Admin Role', N'bi-archive', NULL, 1,
        N'Administrator tools — backups and system maintenance',
        1, @AdminRoles
    );
    SET @ParentID = SCOPE_IDENTITY();
END

IF EXISTS (
    SELECT 1 FROM dbo.MenuMaster
    WHERE ParentMenuID = @ParentID AND MenuName = N'Software Updates'
)
BEGIN
    UPDATE dbo.MenuMaster
    SET MenuURL = N'/admin/software-updates',
        MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-arrow-repeat'),
        DisplayOrder = 8,
        Description = N'Version history, change log, health and rollback',
        IsActive = 1,
        RoleName = @AdminRoles
    WHERE ParentMenuID = @ParentID AND MenuName = N'Software Updates';
END
ELSE IF EXISTS (SELECT 1 FROM dbo.MenuMaster WHERE MenuURL = N'/admin/software-updates')
BEGIN
    UPDATE dbo.MenuMaster
    SET ParentMenuID = @ParentID,
        MenuName = N'Software Updates',
        MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-arrow-repeat'),
        DisplayOrder = 8,
        IsActive = 1,
        RoleName = @AdminRoles
    WHERE MenuURL = N'/admin/software-updates';
END
ELSE
BEGIN
    INSERT INTO dbo.MenuMaster (
        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
        Description, IsActive, RoleName
    )
    VALUES (
        @ParentID,
        N'Software Updates',
        N'bi-arrow-repeat',
        N'/admin/software-updates',
        8,
        N'Version history, change log, health and rollback',
        1,
        @AdminRoles
    );
END
GO

/* About Software page under Admin Role */
DECLARE @ParentID2 INT;
DECLARE @AdminRoles2 NVARCHAR(50) = N'Administrator,Admin';

SELECT TOP 1 @ParentID2 = MenuID
FROM dbo.MenuMaster
WHERE MenuName = N'Admin Role'
  AND ParentMenuID IS NULL
ORDER BY MenuID;

IF @ParentID2 IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM dbo.MenuMaster WHERE MenuURL = N'/admin/about-software')
BEGIN
    INSERT INTO dbo.MenuMaster (
        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
        Description, IsActive, RoleName
    )
    VALUES (
        @ParentID2,
        N'About Software',
        N'bi-info-circle',
        N'/admin/about-software',
        9,
        N'Application version and release information',
        1,
        @AdminRoles2
    );
END
GO
