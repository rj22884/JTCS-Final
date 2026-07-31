/*
    Stamp Activity menu + stamp report shortcuts under Reports.

    Stamp Activity is a child of Activities (not top-level SHCIL).
    Safe for fresh DBs; already-applied DBs are tracked in SchemaMigration
    and get the Activities hierarchy from 067_stamp_activity_under_activities.sql.
*/
SET NOCOUNT ON;

BEGIN TRANSACTION;

/* Remove legacy SHCIL stamp children only — do not delete Stamp Activity if already under Activities */
DELETE FROM dbo.MenuMaster
WHERE MenuName IN (N'Stamp Purchase', N'e-Stamp Issue', N'SHCIL Ledger')
   OR (
        MenuName = N'Stamp Activity'
        AND ParentMenuID IN (
            SELECT MenuID FROM dbo.MenuMaster WHERE MenuName = N'SHCIL'
        )
   );

DECLARE @ActivitiesID INT = (
    SELECT TOP 1 MenuID
    FROM dbo.MenuMaster
    WHERE MenuName = N'Activities' AND ParentMenuID IS NULL
    ORDER BY MenuID
);

IF @ActivitiesID IS NULL
BEGIN
    INSERT INTO dbo.MenuMaster (MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
    VALUES (N'Activities', N'bi-lightning-charge', NULL, 2, N'Daily operational activities', 1, NULL);
    SET @ActivitiesID = SCOPE_IDENTITY();
END;

IF NOT EXISTS (
    SELECT 1
    FROM dbo.MenuMaster
    WHERE MenuName = N'Stamp Activity'
      AND ParentMenuID = @ActivitiesID
)
BEGIN
    /* Re-parent existing row if present elsewhere; else insert */
    IF EXISTS (SELECT 1 FROM dbo.MenuMaster WHERE MenuName = N'Stamp Activity' OR MenuURL = N'/shcil/stamp-activity')
    BEGIN
        UPDATE dbo.MenuMaster
        SET ParentMenuID = @ActivitiesID,
            MenuName = N'Stamp Activity',
            MenuURL = N'/shcil/stamp-activity',
            MenuIcon = N'bi-file-earmark-ruled',
            Description = N'Uttarakhand e-Stamp manual entry and OCR',
            IsActive = 1,
            DisplayOrder = 0
        WHERE MenuID = (
            SELECT TOP 1 MenuID
            FROM dbo.MenuMaster
            WHERE MenuURL = N'/shcil/stamp-activity' OR MenuName = N'Stamp Activity'
            ORDER BY CASE WHEN MenuURL = N'/shcil/stamp-activity' THEN 0 ELSE 1 END, MenuID
        );
    END
    ELSE
    BEGIN
        INSERT INTO dbo.MenuMaster (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
        VALUES (@ActivitiesID, N'Stamp Activity', N'bi-file-earmark-ruled', N'/shcil/stamp-activity', 0,
                N'Uttarakhand e-Stamp manual entry and OCR', 1, NULL);
    END
END
ELSE
BEGIN
    UPDATE dbo.MenuMaster
    SET MenuURL = N'/shcil/stamp-activity',
        MenuIcon = N'bi-file-earmark-ruled',
        Description = N'Uttarakhand e-Stamp manual entry and OCR',
        IsActive = 1
    WHERE MenuName = N'Stamp Activity' AND ParentMenuID = @ActivitiesID;
END;

/* Hide empty top-level SHCIL if it has no active children */
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

DECLARE @ReportsID INT = (SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Reports' AND ParentMenuID IS NULL);

IF @ReportsID IS NOT NULL
BEGIN
    MERGE dbo.MenuMaster AS target
    USING (VALUES
        (N'Stamp Register', N'bi-journal-text', N'/reports/stamp-register', 20),
        (N'Stamp Sales', N'bi-receipt', N'/reports/stamp-sales', 21),
        (N'Stamp Collection', N'bi-cash-stack', N'/reports/stamp-collection', 22),
        (N'Customer Wise Stamp', N'bi-people', N'/reports/stamp-customer-wise', 23),
        (N'Date Wise Stamp', N'bi-calendar3', N'/reports/stamp-date-wise', 24),
        (N'Payment Mode Wise Stamp', N'bi-credit-card', N'/reports/stamp-payment-mode', 25)
    ) AS src (MenuName, MenuIcon, MenuURL, DisplayOrder)
    ON target.MenuName = src.MenuName AND target.ParentMenuID = @ReportsID
    WHEN MATCHED THEN
        UPDATE SET MenuURL = src.MenuURL, MenuIcon = src.MenuIcon, DisplayOrder = src.DisplayOrder, IsActive = 1
    WHEN NOT MATCHED THEN
        INSERT (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
        VALUES (@ReportsID, src.MenuName, src.MenuIcon, src.MenuURL, src.DisplayOrder, N'SHCIL stamp report', 1, NULL);
END;

COMMIT TRANSACTION;
GO

PRINT '011_stamp_activity_menu.sql completed.';
GO
