/*
    Integration Settings — new table + one Admin Role menu item (idempotent)
*/
USE JTCSS;
GO

IF OBJECT_ID(N'dbo.IntegrationSettings', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.IntegrationSettings (
        SettingID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        Provider NVARCHAR(50) NOT NULL,
        SettingKey NVARCHAR(100) NOT NULL,
        SettingValueEncrypted NVARCHAR(MAX) NULL,
        Description NVARCHAR(300) NULL,
        IsActive BIT NOT NULL CONSTRAINT DF_IntegrationSettings_IsActive DEFAULT (1),
        CreatedOn DATETIME2 NOT NULL CONSTRAINT DF_IntegrationSettings_CreatedOn DEFAULT (SYSUTCDATETIME()),
        ModifiedOn DATETIME2 NULL,
        CONSTRAINT UX_IntegrationSettings_ProviderKey UNIQUE (Provider, SettingKey)
    );
    CREATE INDEX IX_IntegrationSettings_Provider ON dbo.IntegrationSettings (Provider, IsActive);
END;
GO

/* Admin Role → Integration Settings (sibling of Settings; does not alter Settings row) */
DECLARE @AdminRoleID INT = (
    SELECT TOP 1 MenuID
    FROM dbo.MenuMaster
    WHERE MenuName = N'Admin Role'
      AND ParentMenuID IS NULL
    ORDER BY MenuID
);

IF @AdminRoleID IS NOT NULL
   AND NOT EXISTS (
        SELECT 1
        FROM dbo.MenuMaster
        WHERE ParentMenuID = @AdminRoleID
          AND MenuName = N'Integration Settings'
   )
BEGIN
    INSERT INTO dbo.MenuMaster (
        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
        Description, IsActive, RoleName
    )
    VALUES (
        @AdminRoleID,
        N'Integration Settings',
        N'bi-plugin',
        N'/admin/integrations',
        4,
        N'External API credentials and integration configuration',
        1,
        N'Administrator,Admin'
    );
END;
GO

PRINT '075_integration_settings.sql completed.';
GO
