/*
    Ensure eCourt Activity (and Stamp Activity) appear under Activities.
    Fixes VPS where eCourt stayed under hidden top-level SHCIL and vanished from nav.
    DATA safe — MenuMaster rows only.
*/
USE JTCSS;
GO

DECLARE @ActivitiesID INT = (
    SELECT TOP 1 MenuID
    FROM dbo.MenuMaster
    WHERE MenuName = N'Activities' AND ParentMenuID IS NULL
    ORDER BY MenuID
);

IF @ActivitiesID IS NULL
BEGIN
    INSERT INTO dbo.MenuMaster
        (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
    VALUES
        (NULL, N'Activities', N'bi-lightning-charge', NULL, 2,
         N'Daily operational activities', 1, NULL);
    SET @ActivitiesID = SCOPE_IDENTITY();
END
ELSE
BEGIN
    UPDATE dbo.MenuMaster
    SET IsActive = 1,
        MenuIcon = COALESCE(NULLIF(LTRIM(RTRIM(MenuIcon)), N''), N'bi-lightning-charge')
    WHERE MenuID = @ActivitiesID;
END;

/* ---- Stamp Activity ---- */
DECLARE @StampID INT = (
    SELECT TOP 1 MenuID
    FROM dbo.MenuMaster
    WHERE MenuURL = N'/shcil/stamp-activity'
       OR MenuName = N'Stamp Activity'
    ORDER BY CASE WHEN MenuURL = N'/shcil/stamp-activity' THEN 0 ELSE 1 END, MenuID
);

IF @StampID IS NULL
BEGIN
    INSERT INTO dbo.MenuMaster
        (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
    VALUES
        (@ActivitiesID, N'Stamp Activity', N'bi-file-earmark-ruled', N'/shcil/stamp-activity', 0,
         N'Uttarakhand e-Stamp manual entry and OCR', 1, NULL);
END
ELSE
BEGIN
    UPDATE dbo.MenuMaster
    SET ParentMenuID = @ActivitiesID,
        MenuName = N'Stamp Activity',
        MenuURL = N'/shcil/stamp-activity',
        MenuIcon = N'bi-file-earmark-ruled',
        DisplayOrder = 0,
        Description = COALESCE(Description, N'Uttarakhand e-Stamp manual entry and OCR'),
        IsActive = 1,
        RoleName = NULL
    WHERE MenuID = @StampID;
END;

/* ---- eCourt Activity (create if missing; always under Activities) ---- */
DECLARE @EcourtID INT = (
    SELECT TOP 1 MenuID
    FROM dbo.MenuMaster
    WHERE MenuURL = N'/shcil/ecourt-activity'
       OR MenuName IN (N'eCourt Activity', N'e-Court Activity', N'ecourt activity')
    ORDER BY CASE WHEN MenuURL = N'/shcil/ecourt-activity' THEN 0 ELSE 1 END, MenuID
);

IF @EcourtID IS NULL
BEGIN
    INSERT INTO dbo.MenuMaster
        (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
    VALUES
        (@ActivitiesID, N'eCourt Activity', N'bi-file-earmark-text', N'/shcil/ecourt-activity', 1,
         N'SHCIL e-Court fee receipt import and stationery sale check', 1, NULL);
END
ELSE
BEGIN
    UPDATE dbo.MenuMaster
    SET ParentMenuID = @ActivitiesID,
        MenuName = N'eCourt Activity',
        MenuURL = N'/shcil/ecourt-activity',
        MenuIcon = N'bi-file-earmark-text',
        DisplayOrder = 1,
        Description = N'SHCIL e-Court fee receipt import and stationery sale check',
        IsActive = 1,
        RoleName = NULL
    WHERE MenuID = @EcourtID;
END;

/* Hide empty top-level SHCIL */
UPDATE dbo.MenuMaster
SET IsActive = 0
WHERE MenuName = N'SHCIL'
  AND ParentMenuID IS NULL
  AND NOT EXISTS (
        SELECT 1
        FROM dbo.MenuMaster c
        WHERE c.ParentMenuID = MenuMaster.MenuID
          AND c.IsActive = 1
  );

PRINT '080_ensure_ecourt_under_activities.sql completed.';
GO
