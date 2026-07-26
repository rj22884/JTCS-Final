/*
    JTCS ERP - Admin Role backup menu URLs (idempotent)
    Wires existing Admin Role → Backup Full / Data Backup to module routes.
*/

SET NOCOUNT ON;
GO

DECLARE @ParentID INT;

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
        NULL,
        N'Admin Role',
        N'bi-archive',
        NULL,
        1,
        N'Administrator tools — backups and system maintenance',
        1,
        N'Administrator'
    );
    SET @ParentID = SCOPE_IDENTITY();
END
ELSE
BEGIN
    UPDATE dbo.MenuMaster
    SET MenuURL = NULL,
        MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-archive'),
        IsActive = 1,
        RoleName = COALESCE(NULLIF(RoleName, N''), N'Administrator')
    WHERE MenuID = @ParentID;
END;

UPDATE dbo.MenuMaster
SET MenuURL = N'/admin/backup/full',
    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-database-fill'),
    DisplayOrder = 1,
    Description = N'Full application + database backup (ZIP)',
    IsActive = 1
WHERE ParentMenuID = @ParentID
  AND MenuName = N'Backup Full';

IF NOT EXISTS (
    SELECT 1 FROM dbo.MenuMaster
    WHERE ParentMenuID = @ParentID AND MenuName = N'Backup Full'
)
BEGIN
    INSERT INTO dbo.MenuMaster (
        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
        Description, IsActive, RoleName
    )
    VALUES (
        @ParentID,
        N'Backup Full',
        N'bi-database-fill',
        N'/admin/backup/full',
        1,
        N'Full application + database backup (ZIP)',
        1,
        NULL
    );
END;

UPDATE dbo.MenuMaster
SET MenuURL = N'/admin/backup/data',
    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-clipboard-data'),
    DisplayOrder = 2,
    Description = N'SQL Server database backup (.bak)',
    IsActive = 1
WHERE ParentMenuID = @ParentID
  AND MenuName = N'Data Backup';

IF NOT EXISTS (
    SELECT 1 FROM dbo.MenuMaster
    WHERE ParentMenuID = @ParentID AND MenuName = N'Data Backup'
)
BEGIN
    INSERT INTO dbo.MenuMaster (
        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
        Description, IsActive, RoleName
    )
    VALUES (
        @ParentID,
        N'Data Backup',
        N'bi-clipboard-data',
        N'/admin/backup/data',
        2,
        N'SQL Server database backup (.bak)',
        1,
        NULL
    );
END;

PRINT '044_admin_backup_menus.sql completed.';
GO
