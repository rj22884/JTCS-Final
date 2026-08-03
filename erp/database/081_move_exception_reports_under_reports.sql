/*
    Move Stamp Exception and e-Court Exception under Reports and Analysis,
    immediately after Ledger Report. Keeps existing module URLs.

    Hides only the old Exceptional Report parent.
    DATA safe — MenuMaster parent/order/active only. No other modules changed.
*/
USE JTCSS;
GO

UPDATE dbo.MenuMaster
SET IsActive = 0,
    Description = N'Exceptional and special reports (hidden from nav; children under Reports and Analysis)'
WHERE MenuName = N'Exceptional Report'
  AND ParentMenuID IS NULL;
GO

DECLARE @ReportsID INT;
DECLARE @LedgerOrder INT;
DECLARE @StampOrder INT;
DECLARE @EcourtOrder INT;

SELECT TOP 1 @ReportsID = MenuID
FROM dbo.MenuMaster
WHERE ParentMenuID IS NULL
  AND (
        MenuURL = N'/Reports_and_analysis'
     OR MenuName IN (N'Reports and Analysis', N'Reports & Analysis', N'Reports_and_analysis')
  )
ORDER BY MenuID;

IF @ReportsID IS NULL
BEGIN
    INSERT INTO dbo.MenuMaster
        (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
    VALUES (NULL, N'Reports and Analysis', N'bi-graph-up', NULL, 50, N'Reports and analysis', 1, NULL);
    SET @ReportsID = SCOPE_IDENTITY();
END
ELSE
    UPDATE dbo.MenuMaster SET IsActive = 1 WHERE MenuID = @ReportsID;

IF NOT EXISTS (
    SELECT 1 FROM dbo.MenuMaster
    WHERE MenuURL = N'/Reports_and_analysis/ledger_report' OR MenuName = N'Ledger Report'
)
    INSERT INTO dbo.MenuMaster
        (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
    VALUES (
        @ReportsID, N'Ledger Report', N'bi-journal-text',
        N'/Reports_and_analysis/ledger_report', 10,
        N'Search and preview bank, customer, work/category and item ledgers', 1, NULL
    );
ELSE
    UPDATE dbo.MenuMaster
    SET ParentMenuID = @ReportsID, MenuName = N'Ledger Report',
        MenuURL = N'/Reports_and_analysis/ledger_report',
        MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-journal-text'),
        IsActive = 1
    WHERE MenuURL = N'/Reports_and_analysis/ledger_report' OR MenuName = N'Ledger Report';

SELECT @LedgerOrder = MAX(DisplayOrder)
FROM dbo.MenuMaster
WHERE ParentMenuID = @ReportsID
  AND (MenuURL = N'/Reports_and_analysis/ledger_report' OR MenuName = N'Ledger Report');

SET @StampOrder = ISNULL(@LedgerOrder, 10) + 10;
SET @EcourtOrder = @StampOrder + 10;

IF EXISTS (
    SELECT 1 FROM dbo.MenuMaster
    WHERE MenuURL = N'/exceptional-report/stamp-certificate'
       OR MenuName IN (N'Stamp Exception', N'Stamp Certificate Reconciliation')
)
    UPDATE dbo.MenuMaster
    SET ParentMenuID = @ReportsID,
        MenuName = N'Stamp Exception',
        MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-file-earmark-spreadsheet'),
        MenuURL = N'/exceptional-report/stamp-certificate',
        DisplayOrder = @StampOrder,
        Description = N'SHCIL stamp certificate reconciliation',
        IsActive = 1,
        RoleName = NULL
    WHERE MenuURL = N'/exceptional-report/stamp-certificate'
       OR MenuName IN (N'Stamp Exception', N'Stamp Certificate Reconciliation');
ELSE
    INSERT INTO dbo.MenuMaster
        (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
    VALUES (
        @ReportsID, N'Stamp Exception', N'bi-file-earmark-spreadsheet',
        N'/exceptional-report/stamp-certificate', @StampOrder,
        N'SHCIL stamp certificate reconciliation', 1, NULL
    );

IF EXISTS (
    SELECT 1 FROM dbo.MenuMaster
    WHERE MenuURL = N'/exceptional-report/ecourt-exception'
       OR MenuName IN (N'e-Court Exception', N'E-Court Exception')
)
    UPDATE dbo.MenuMaster
    SET ParentMenuID = @ReportsID,
        MenuName = N'e-Court Exception',
        MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-journal-check'),
        MenuURL = N'/exceptional-report/ecourt-exception',
        DisplayOrder = @EcourtOrder,
        Description = N'e-Court exceptional report',
        IsActive = 1,
        RoleName = NULL
    WHERE MenuURL = N'/exceptional-report/ecourt-exception'
       OR MenuName IN (N'e-Court Exception', N'E-Court Exception');
ELSE
    INSERT INTO dbo.MenuMaster
        (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
    VALUES (
        @ReportsID, N'e-Court Exception', N'bi-journal-check',
        N'/exceptional-report/ecourt-exception', @EcourtOrder,
        N'e-Court exceptional report', 1, NULL
    );

UPDATE dbo.MenuMaster
SET IsActive = 0
WHERE MenuURL LIKE N'/exceptional-report/%'
  AND MenuURL NOT IN (
        N'/exceptional-report/stamp-certificate',
        N'/exceptional-report/ecourt-exception'
  );

;WITH d AS (
    SELECT MenuID,
           ROW_NUMBER() OVER (PARTITION BY MenuURL ORDER BY MenuID) AS rn
    FROM dbo.MenuMaster
    WHERE MenuURL IN (
        N'/exceptional-report/stamp-certificate',
        N'/exceptional-report/ecourt-exception'
    )
)
UPDATE m
SET IsActive = 0
FROM dbo.MenuMaster m
INNER JOIN d ON d.MenuID = m.MenuID
WHERE d.rn > 1;
GO

PRINT '081_move_exception_reports_under_reports.sql completed.';
GO
