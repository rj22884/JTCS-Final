-- Admin Role → Sales Executive Applications
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
        NULL, N'Admin Role', N'bi-archive', NULL, 1,
        N'Administrator tools — backups and system maintenance',
        1, @AdminRoles
    );
    SET @ParentID = SCOPE_IDENTITY();
END;

IF NOT EXISTS (
    SELECT 1 FROM dbo.MenuMaster
    WHERE ParentMenuID = @ParentID AND MenuName = N'Sales Executive Applications'
)
AND NOT EXISTS (
    SELECT 1 FROM dbo.MenuMaster WHERE MenuURL = N'/admin/recruitment'
)
BEGIN
    INSERT INTO dbo.MenuMaster (
        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
        Description, IsActive, RoleName
    )
    VALUES (
        @ParentID,
        N'Sales Executive Applications',
        N'bi-briefcase',
        N'/admin/recruitment',
        66,
        N'Website Sales Executive job applications',
        1,
        @AdminRoles
    );
END;

IF NOT EXISTS (
    SELECT 1 FROM dbo.MenuMaster
    WHERE ParentMenuID = @ParentID AND MenuName = N'Recruitment Admin Login'
)
BEGIN
    INSERT INTO dbo.MenuMaster (
        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
        Description, IsActive, RoleName
    )
    VALUES (
        @ParentID,
        N'Recruitment Admin Login',
        N'bi-box-arrow-up-right',
        N'/admin/recruitment/admin-login',
        67,
        N'Open website recruitment admin login',
        1,
        @AdminRoles
    );
END;
GO
