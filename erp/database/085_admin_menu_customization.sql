/*
    JTCS ERP - Admin Role → Menu Customization (idempotent)
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
      AND MenuName = N'Menu Customization'
)
BEGIN
    UPDATE dbo.MenuMaster
    SET MenuURL = N'/admin/menu-customization',
        MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-ui-checks-grid'),
        DisplayOrder = 55,
        Description = N'Customize main ribbon menus — reorder, add, remove',
        IsActive = 1,
        RoleName = @AdminRoles
    WHERE ParentMenuID = @ParentID
      AND MenuName = N'Menu Customization';
END
ELSE IF NOT EXISTS (
    SELECT 1 FROM dbo.MenuMaster WHERE MenuURL = N'/admin/menu-customization'
)
BEGIN
    INSERT INTO dbo.MenuMaster (
        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
        Description, IsActive, RoleName
    )
    VALUES (
        @ParentID,
        N'Menu Customization',
        N'bi-ui-checks-grid',
        N'/admin/menu-customization',
        55,
        N'Customize main ribbon menus — reorder, add, remove',
        1,
        @AdminRoles
    );
END
ELSE
BEGIN
    UPDATE dbo.MenuMaster
    SET ParentMenuID = @ParentID,
        MenuName = N'Menu Customization',
        MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-ui-checks-grid'),
        DisplayOrder = 55,
        Description = N'Customize main ribbon menus — reorder, add, remove',
        IsActive = 1,
        RoleName = @AdminRoles
    WHERE MenuURL = N'/admin/menu-customization';
END;

PRINT '085_admin_menu_customization.sql completed.';
GO
