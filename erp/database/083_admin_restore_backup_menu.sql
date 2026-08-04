/*
    JTCS ERP - Admin Role → Restore Backup menu (idempotent)
*/

SET NOCOUNT ON;
GO

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
        NULL,
        N'Admin Role',
        N'bi-archive',
        NULL,
        1,
        N'Administrator tools — backups and system maintenance',
        1,
        @AdminRoles
    );
    SET @ParentID = SCOPE_IDENTITY();
END;

IF EXISTS (
    SELECT 1 FROM dbo.MenuMaster
    WHERE ParentMenuID = @ParentID
      AND MenuName = N'Restore Backup'
)
BEGIN
    UPDATE dbo.MenuMaster
    SET MenuURL = N'/admin/backup/restore',
        MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-arrow-counterclockwise'),
        DisplayOrder = 3,
        Description = N'Upload VPS backup and restore on this local PC',
        IsActive = 1,
        RoleName = @AdminRoles
    WHERE ParentMenuID = @ParentID
      AND MenuName = N'Restore Backup';
END
ELSE IF NOT EXISTS (
    SELECT 1 FROM dbo.MenuMaster WHERE MenuURL = N'/admin/backup/restore'
)
BEGIN
    INSERT INTO dbo.MenuMaster (
        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
        Description, IsActive, RoleName
    )
    VALUES (
        @ParentID,
        N'Restore Backup',
        N'bi-arrow-counterclockwise',
        N'/admin/backup/restore',
        3,
        N'Upload VPS backup and restore on this local PC',
        1,
        @AdminRoles
    );
END
ELSE
BEGIN
    UPDATE dbo.MenuMaster
    SET ParentMenuID = @ParentID,
        MenuName = N'Restore Backup',
        MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-arrow-counterclockwise'),
        DisplayOrder = 3,
        Description = N'Upload VPS backup and restore on this local PC',
        IsActive = 1,
        RoleName = @AdminRoles
    WHERE MenuURL = N'/admin/backup/restore';
END;

PRINT '083_admin_restore_backup_menu.sql completed.';
GO
