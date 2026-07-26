/*
    Exceptional Report submenu for SHCIL stamp certificate reconciliation.
*/
USE JTCSS;
GO

SET NOCOUNT ON;
GO

DECLARE @ParentID INT = (
    SELECT TOP 1 MenuID
    FROM dbo.MenuMaster
    WHERE MenuName = N'Exceptional Report'
      AND ParentMenuID IS NULL
);

IF @ParentID IS NOT NULL
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM dbo.MenuMaster
        WHERE ParentMenuID = @ParentID
          AND MenuURL = N'/exceptional-report/stamp-certificate'
    )
    BEGIN
        INSERT INTO dbo.MenuMaster (
            ParentMenuID,
            MenuName,
            MenuIcon,
            MenuURL,
            DisplayOrder,
            Description,
            IsActive,
            RoleName
        )
        VALUES (
            @ParentID,
            N'Stamp Certificate Reconciliation',
            N'bi-file-earmark-spreadsheet',
            N'/exceptional-report/stamp-certificate',
            1,
            N'Compare SHCIL CSV certificates with Stamp Activity in JTCS',
            1,
            NULL
        );
    END
    ELSE
    BEGIN
        UPDATE dbo.MenuMaster
        SET MenuName = N'Stamp Certificate Reconciliation',
            MenuIcon = N'bi-file-earmark-spreadsheet',
            DisplayOrder = 1,
            Description = N'Compare SHCIL CSV certificates with Stamp Activity in JTCS',
            IsActive = 1
        WHERE ParentMenuID = @ParentID
          AND MenuURL = N'/exceptional-report/stamp-certificate';
    END
END;
GO

PRINT '038_exceptional_stamp_report_menu.sql completed.';
GO
