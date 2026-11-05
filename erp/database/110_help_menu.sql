/*
    Admin Role → Help (all signed-in users). RoleName NULL.
    DATA safe — MenuMaster only. Does not change other modules.
*/
USE JTCSS;
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
        NULL, N'Admin Role', N'bi-archive', NULL, 1,
        N'Administrator tools', 1, N'Administrator,Admin'
    );
    SET @ParentID = SCOPE_IDENTITY();
END;

IF EXISTS (
    SELECT 1 FROM dbo.MenuMaster
    WHERE MenuURL = N'/help' OR (MenuName = N'Help' AND ParentMenuID = @ParentID)
)
BEGIN
    UPDATE dbo.MenuMaster
    SET ParentMenuID = @ParentID,
        MenuName = N'Help',
        MenuIcon = N'bi-question-circle',
        MenuURL = N'/help',
        DisplayOrder = 0,
        Description = N'User help for every menu, screen, and calculation',
        IsActive = 1,
        RoleName = NULL
    WHERE MenuURL = N'/help' OR MenuName = N'Help';
END
ELSE
BEGIN
    INSERT INTO dbo.MenuMaster (
        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
        Description, IsActive, RoleName
    )
    VALUES (
        @ParentID, N'Help', N'bi-question-circle', N'/help', 0,
        N'User help for every menu, screen, and calculation',
        1, NULL
    );
END;
GO

PRINT '110_help_menu.sql completed.';
GO
