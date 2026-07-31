/*
    Stamp Activity / eCourt Activity belong under Activities (not top-level SHCIL).

    Local Menu Admin already uses: Activities → Stamp Activity.
    Deploy seeds 003/011 historically created SHCIL as a main menu with Stamp under it.
    This migration aligns production MenuMaster with the local hierarchy without
    touching other modules (Employee, Stock, GST, etc.).
*/
SET NOCOUNT ON;

BEGIN TRANSACTION;

/* ---- ensure Activities top-level parent ---- */
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
        MenuIcon = COALESCE(NULLIF(LTRIM(RTRIM(MenuIcon)), N''), N'bi-lightning-charge'),
        Description = COALESCE(Description, N'Daily operational activities')
    WHERE MenuID = @ActivitiesID;
END;

/* ---- Stamp Activity → Activities ---- */
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
        Description = COALESCE(Description, N'Uttarakhand e-Stamp manual entry and OCR'),
        IsActive = 1,
        DisplayOrder = CASE
            WHEN ParentMenuID = @ActivitiesID THEN DisplayOrder
            ELSE 0
        END
    WHERE MenuID = @StampID;
END;

/* ---- eCourt / e-Court Activity → Activities (same local layout) ---- */
DECLARE @EcourtID INT = (
    SELECT TOP 1 MenuID
    FROM dbo.MenuMaster
    WHERE MenuURL = N'/shcil/ecourt-activity'
       OR MenuName IN (N'eCourt Activity', N'e-Court Activity')
    ORDER BY CASE WHEN MenuURL = N'/shcil/ecourt-activity' THEN 0 ELSE 1 END, MenuID
);

IF @EcourtID IS NOT NULL
BEGIN
    UPDATE dbo.MenuMaster
    SET ParentMenuID = @ActivitiesID,
        MenuURL = N'/shcil/ecourt-activity',
        MenuIcon = COALESCE(NULLIF(LTRIM(RTRIM(MenuIcon)), N''), N'bi-file-earmark-text'),
        IsActive = 1,
        DisplayOrder = CASE
            WHEN ParentMenuID = @ActivitiesID THEN DisplayOrder
            ELSE 1
        END
    WHERE MenuID = @EcourtID;
END;

/* ---- hide empty top-level SHCIL (no active children left) ---- */
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

COMMIT TRANSACTION;
GO

PRINT '067_stamp_activity_under_activities.sql completed.';
GO
