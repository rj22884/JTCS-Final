-- Admin Role → Client/Customer Activity menu
-- Idempotent: safe to re-run.

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
END
ELSE
BEGIN
    UPDATE dbo.MenuMaster
    SET RoleName = @AdminRoles,
        IsActive = 1
    WHERE MenuID = @ParentID;
END;

IF EXISTS (
    SELECT 1 FROM dbo.MenuMaster
    WHERE ParentMenuID = @ParentID AND MenuName = N'Client/Customer Activity'
)
BEGIN
    UPDATE dbo.MenuMaster
    SET MenuURL = N'/admin/customer-activity',
        MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-person-check'),
        DisplayOrder = 12,
        Description = N'Customer Portal login and activation activity',
        IsActive = 1,
        RoleName = @AdminRoles
    WHERE ParentMenuID = @ParentID AND MenuName = N'Client/Customer Activity';
END
ELSE IF EXISTS (
    SELECT 1 FROM dbo.MenuMaster WHERE MenuURL = N'/admin/customer-activity'
)
BEGIN
    UPDATE dbo.MenuMaster
    SET ParentMenuID = @ParentID,
        MenuName = N'Client/Customer Activity',
        MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-person-check'),
        DisplayOrder = 12,
        Description = N'Customer Portal login and activation activity',
        IsActive = 1,
        RoleName = @AdminRoles
    WHERE MenuURL = N'/admin/customer-activity';
END
ELSE
BEGIN
    INSERT INTO dbo.MenuMaster (
        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
        Description, IsActive, RoleName
    )
    VALUES (
        @ParentID,
        N'Client/Customer Activity',
        N'bi-person-check',
        N'/admin/customer-activity',
        12,
        N'Customer Portal login and activation activity',
        1,
        @AdminRoles
    );
END;
GO
