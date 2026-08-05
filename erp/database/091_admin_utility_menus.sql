/*
    JTCS ERP — Admin Role → Utility menus (idempotent)
    Sync child label is set by app ensure (Upload VPS locally / Download Local on VPS).
*/
SET NOCOUNT ON;
GO

DECLARE @ParentID INT;
DECLARE @UtilityID INT;
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
        N'Administrator tools', 1, @AdminRoles
    );
    SET @ParentID = SCOPE_IDENTITY();
END;

IF EXISTS (
    SELECT 1 FROM dbo.MenuMaster
    WHERE ParentMenuID = @ParentID AND MenuName = N'Utility'
)
BEGIN
    UPDATE dbo.MenuMaster
    SET MenuURL = N'/admin/utility',
        MenuIcon = N'bi-tools',
        DisplayOrder = 60,
        Description = N'Local/VPS sync and maintenance tools',
        IsActive = 1,
        RoleName = @AdminRoles
    WHERE ParentMenuID = @ParentID AND MenuName = N'Utility';
END
ELSE IF NOT EXISTS (
    SELECT 1 FROM dbo.MenuMaster WHERE MenuURL = N'/admin/utility'
)
BEGIN
    INSERT INTO dbo.MenuMaster (
        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
        Description, IsActive, RoleName
    )
    VALUES (
        @ParentID, N'Utility', N'bi-tools', N'/admin/utility', 60,
        N'Local/VPS sync and maintenance tools', 1, @AdminRoles
    );
END
ELSE
BEGIN
    UPDATE dbo.MenuMaster
    SET ParentMenuID = @ParentID,
        MenuName = N'Utility',
        MenuIcon = N'bi-tools',
        DisplayOrder = 60,
        Description = N'Local/VPS sync and maintenance tools',
        IsActive = 1,
        RoleName = @AdminRoles
    WHERE MenuURL = N'/admin/utility';
END;

SELECT TOP 1 @UtilityID = MenuID
FROM dbo.MenuMaster
WHERE ParentMenuID = @ParentID
  AND (MenuName = N'Utility' OR MenuURL = N'/admin/utility')
ORDER BY MenuID;

IF @UtilityID IS NOT NULL
BEGIN
    IF NOT EXISTS (SELECT 1 FROM dbo.MenuMaster WHERE MenuURL = N'/admin/utility/sync')
        INSERT INTO dbo.MenuMaster (
            ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
            Description, IsActive, RoleName
        )
        VALUES (
            @UtilityID, N'Upload VPS', N'bi-cloud-arrow-up', N'/admin/utility/sync', 1,
            N'Push code and deploy to VPS (label flips on VPS)', 1, @AdminRoles
        );

    IF NOT EXISTS (
        SELECT 1 FROM dbo.MenuMaster
        WHERE ParentMenuID = @UtilityID AND MenuURL = N'/admin/utility/clear-cache'
    )
        INSERT INTO dbo.MenuMaster (
            ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
            Description, IsActive, RoleName
        )
        VALUES (
            @UtilityID, N'Clear Cache', N'bi-trash', N'/admin/utility/clear-cache', 2,
            N'Clear Python/template caches', 1, @AdminRoles
        );

    IF NOT EXISTS (
        SELECT 1 FROM dbo.MenuMaster
        WHERE ParentMenuID = @UtilityID AND MenuURL = N'/admin/utility/health'
    )
        INSERT INTO dbo.MenuMaster (
            ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
            Description, IsActive, RoleName
        )
        VALUES (
            @UtilityID, N'System Health', N'bi-heart-pulse', N'/admin/utility/health', 3,
            N'Database and public health checks', 1, @AdminRoles
        );

    IF NOT EXISTS (
        SELECT 1 FROM dbo.MenuMaster
        WHERE ParentMenuID = @UtilityID AND MenuURL = N'/admin/utility/info'
    )
        INSERT INTO dbo.MenuMaster (
            ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
            Description, IsActive, RoleName
        )
        VALUES (
            @UtilityID, N'App Info', N'bi-info-circle', N'/admin/utility/info', 4,
            N'Runtime mode, paths, VPS target', 1, @AdminRoles
        );
END;

PRINT '091_admin_utility_menus.sql completed.';
GO
