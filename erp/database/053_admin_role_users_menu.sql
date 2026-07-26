/*

    Admin Role → Users menu (after Settings) → /admin/users

*/

USE JTCSS;

GO



SET NOCOUNT ON;



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

END;



IF EXISTS (

    SELECT 1

    FROM dbo.MenuMaster

    WHERE ParentMenuID = @ParentID

      AND MenuName = N'Users'

)

BEGIN

    UPDATE dbo.MenuMaster

    SET MenuURL = N'/admin/users',

        MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-people'),

        DisplayOrder = 4,

        Description = N'All users — review status and approve pending registrations',

        IsActive = 1,

        RoleName = N'Administrator,Admin'

    WHERE ParentMenuID = @ParentID

      AND MenuName = N'Users';

END

ELSE IF EXISTS (

    SELECT 1 FROM dbo.MenuMaster

    WHERE MenuURL IN (N'/admin/users', N'/admin/users/pending')

)

BEGIN

    UPDATE dbo.MenuMaster

    SET ParentMenuID = @ParentID,

        MenuName = N'Users',

        MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-people'),

        MenuURL = N'/admin/users',

        DisplayOrder = 4,

        Description = N'All users — review status and approve pending registrations',

        IsActive = 1,

        RoleName = N'Administrator,Admin'

    WHERE MenuURL IN (N'/admin/users', N'/admin/users/pending');

END

ELSE

BEGIN

    INSERT INTO dbo.MenuMaster (

        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,

        Description, IsActive, RoleName

    )

    VALUES (

        @ParentID,

        N'Users',

        N'bi-people',

        N'/admin/users',

        4,

        N'All users — review status and approve pending registrations',

        1,

        N'Administrator,Admin'

    );

END;



PRINT '053_admin_role_users_menu.sql completed.';

GO

