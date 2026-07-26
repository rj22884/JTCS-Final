/*

    Admin Role → Admin Dashboard menu (idempotent)

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

      AND MenuName = N'Admin Dashboard'

)

BEGIN

    UPDATE dbo.MenuMaster

    SET MenuURL = N'/admin/dashboard',

        MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-speedometer2'),

        DisplayOrder = 0,

        Description = N'Administrator dashboard — bank closings and key totals',

        IsActive = 1,

        RoleName = NULL

    WHERE ParentMenuID = @ParentID

      AND MenuName = N'Admin Dashboard';

END

ELSE IF EXISTS (

    SELECT 1 FROM dbo.MenuMaster WHERE MenuURL = N'/admin/dashboard'

)

BEGIN

    UPDATE dbo.MenuMaster

    SET ParentMenuID = @ParentID,

        MenuName = N'Admin Dashboard',

        MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-speedometer2'),

        DisplayOrder = 0,

        Description = N'Administrator dashboard — bank closings and key totals',

        IsActive = 1,

        RoleName = NULL

    WHERE MenuURL = N'/admin/dashboard';

END

ELSE

BEGIN

    INSERT INTO dbo.MenuMaster (

        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,

        Description, IsActive, RoleName

    )

    VALUES (

        @ParentID,

        N'Admin Dashboard',

        N'bi-speedometer2',

        N'/admin/dashboard',

        0,

        N'Administrator dashboard — bank closings and key totals',

        1,

        NULL

    );

END;



PRINT '052_admin_dashboard_menu.sql completed.';

GO

