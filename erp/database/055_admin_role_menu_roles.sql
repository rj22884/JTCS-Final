/*
    Restrict Admin Role menu (and all children) to Administrator + Admin only.
    RoleName NULL previously meant "all roles", which incorrectly showed Admin Role to Operators.
*/
USE JTCSS;
GO

DECLARE @AdminRoles NVARCHAR(50) = N'Administrator,Admin';
DECLARE @ParentID INT;

SELECT TOP 1 @ParentID = MenuID
FROM dbo.MenuMaster
WHERE MenuName = N'Admin Role'
  AND ParentMenuID IS NULL
ORDER BY MenuID;

IF @ParentID IS NOT NULL
BEGIN
    UPDATE dbo.MenuMaster
    SET RoleName = @AdminRoles,
        IsActive = 1
    WHERE MenuID = @ParentID;

    UPDATE dbo.MenuMaster
    SET RoleName = @AdminRoles
    WHERE ParentMenuID = @ParentID;
END;
GO

PRINT '055_admin_role_menu_roles.sql completed.';
GO
