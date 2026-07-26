/*
    Move Menu Admin (Settings) under Admin Role as 3rd item.
*/
USE JTCSS;
GO

DECLARE @ParentID INT;

SELECT TOP 1 @ParentID = MenuID
FROM dbo.MenuMaster
WHERE MenuName = N'Admin Role'
  AND ParentMenuID IS NULL
ORDER BY MenuID;

IF @ParentID IS NOT NULL
BEGIN
    IF EXISTS (
        SELECT 1
        FROM dbo.MenuMaster
        WHERE ParentMenuID = @ParentID
          AND MenuName = N'Settings'
    )
    BEGIN
        UPDATE dbo.MenuMaster
        SET MenuURL = N'/admin/menus',
            MenuIcon = N'bi-gear',
            DisplayOrder = 3,
            IsActive = 1,
            RoleName = NULL,
            Description = COALESCE(Description, N'Menu management and system settings')
        WHERE ParentMenuID = @ParentID
          AND MenuName = N'Settings';
    END
    ELSE
    BEGIN
        INSERT INTO dbo.MenuMaster (
            ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
            Description, IsActive, RoleName
        )
        VALUES (
            @ParentID,
            N'Settings',
            N'bi-gear',
            N'/admin/menus',
            3,
            N'Menu management and system settings',
            1,
            NULL
        );
    END
END;
GO

/* Ensure visible for Admin + Administrator (same as Backup menus). */
UPDATE dbo.MenuMaster
SET RoleName = NULL,
    IsActive = 1,
    DisplayOrder = 3,
    MenuURL = N'/admin/menus',
    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-gear')
WHERE MenuName = N'Settings'
  AND ParentMenuID = (
      SELECT TOP 1 MenuID
      FROM dbo.MenuMaster
      WHERE MenuName = N'Admin Role'
        AND ParentMenuID IS NULL
      ORDER BY MenuID
  );
GO

PRINT '051_admin_role_settings_menu.sql completed.';
GO
