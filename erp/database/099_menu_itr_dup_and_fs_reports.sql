/*
    099 — Menu-only:
    1) Hide duplicate Masters → ITR Followup Master (direct child of Masters,
       after Item Master). Keep Masters → Followup Master → ITR Followup Master.
    2) Ledger Report under Financial Statements as DisplayOrder 1.
    3) One e-Court Exception under Reports and Analysis, immediately before
       Stamp Exception. Financial Statements stays last among Reports children.
    Does not change URLs, roles, or other menus.
*/
SET NOCOUNT ON;

DECLARE @MastersID INT = (
    SELECT TOP 1 MenuID
    FROM dbo.MenuMaster
    WHERE MenuName = N'Masters' AND ParentMenuID IS NULL
    ORDER BY MenuID
);

IF @MastersID IS NOT NULL
BEGIN
    DELETE FROM dbo.MenuMaster
    WHERE ParentMenuID = @MastersID
      AND MenuName = N'ITR Followup Master';
END;

DECLARE @ReportsID INT = (
    SELECT TOP 1 MenuID
    FROM dbo.MenuMaster
    WHERE ParentMenuID IS NULL
      AND (
            MenuURL = N'/Reports_and_analysis'
         OR MenuName IN (
                N'Reports and Analysis',
                N'Reports & Analysis',
                N'Reports_and_analysis'
            )
      )
    ORDER BY MenuID
);

DECLARE @FsID INT = (
    SELECT TOP 1 MenuID
    FROM dbo.MenuMaster
    WHERE @ReportsID IS NOT NULL
      AND ParentMenuID = @ReportsID
      AND (
            MenuName IN (N'Financial Statements', N'Financial Reports')
         OR MenuURL = N'/Reports_and_analysis/financial-statements'
      )
    ORDER BY MenuID
);

IF @FsID IS NOT NULL
BEGIN
    UPDATE dbo.MenuMaster
    SET ParentMenuID = @FsID,
        MenuName = N'Ledger Report',
        DisplayOrder = 1,
        IsActive = 1
    WHERE MenuURL = N'/Reports_and_analysis/ledger_report'
       OR MenuName = N'Ledger Report';

    UPDATE dbo.MenuMaster
    SET DisplayOrder = CASE MenuName
        WHEN N'Balance Sheet' THEN 10
        WHEN N'Profit & Loss' THEN 11
        WHEN N'Trial Balance' THEN 12
        WHEN N'Trading Account' THEN 13
        WHEN N'Cash Flow' THEN 14
        WHEN N'Fund Flow' THEN 15
        WHEN N'Depreciation Chart' THEN 16
        WHEN N'Schedule of Fixed Assets' THEN 17
        WHEN N'Ratio Analysis' THEN 18
        ELSE DisplayOrder
    END
    WHERE ParentMenuID = @FsID
      AND MenuName NOT IN (N'Ledger Report', N'e-Court Exception', N'E-Court Exception');
END;

/* e-Court Exception: one row under Reports, immediately before Stamp Exception */
IF @ReportsID IS NOT NULL
BEGIN
    DECLARE @KeepEcourt INT;
    SELECT TOP 1 @KeepEcourt = MenuID
    FROM dbo.MenuMaster
    WHERE MenuURL = N'/exceptional-report/ecourt-exception'
       OR MenuName IN (N'e-Court Exception', N'E-Court Exception')
    ORDER BY MenuID;

    DELETE FROM dbo.MenuMaster
    WHERE (
            MenuURL = N'/exceptional-report/ecourt-exception'
         OR MenuName IN (N'e-Court Exception', N'E-Court Exception')
          )
      AND (@KeepEcourt IS NULL OR MenuID <> @KeepEcourt);

    IF @KeepEcourt IS NOT NULL
        UPDATE dbo.MenuMaster
        SET ParentMenuID = @ReportsID,
            MenuName = N'e-Court Exception',
            DisplayOrder = 1,
            IsActive = 1
        WHERE MenuID = @KeepEcourt;
    ELSE
        INSERT INTO dbo.MenuMaster (
            ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
            Description, IsActive, RoleName
        )
        VALUES (
            @ReportsID, N'e-Court Exception', N'bi-journal-check',
            N'/exceptional-report/ecourt-exception', 1,
            N'e-Court exceptional report', 1, NULL
        );

    UPDATE dbo.MenuMaster
    SET ParentMenuID = @ReportsID,
        MenuName = N'Stamp Exception',
        DisplayOrder = 2,
        IsActive = 1
    WHERE MenuURL = N'/exceptional-report/stamp-certificate'
       OR MenuName IN (N'Stamp Exception', N'Stamp Certificate Reconciliation');

    IF @FsID IS NOT NULL
    BEGIN
        DECLARE @FsLast INT = (
            SELECT 1 + ISNULL(MAX(DisplayOrder), 0)
            FROM dbo.MenuMaster
            WHERE ParentMenuID = @ReportsID
              AND MenuID <> @FsID
              AND ISNULL(IsActive, 0) = 1
        );
        UPDATE dbo.MenuMaster SET DisplayOrder = @FsLast WHERE MenuID = @FsID;
    END;
END;
GO
