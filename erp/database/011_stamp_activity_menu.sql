/*
    Replace legacy SHCIL stamp menus with new Stamp Activity module + reports
*/
SET NOCOUNT ON;

BEGIN TRANSACTION;

DELETE FROM dbo.MenuMaster
WHERE ParentMenuID IN (SELECT MenuID FROM dbo.MenuMaster WHERE MenuName = N'SHCIL')
   OR MenuName IN (N'Stamp Purchase', N'e-Stamp Issue', N'SHCIL Ledger', N'Stamp Activity');

DECLARE @ShcilID INT = (SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'SHCIL' AND ParentMenuID IS NULL);

IF @ShcilID IS NULL
BEGIN
    INSERT INTO dbo.MenuMaster (MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
    VALUES (N'SHCIL', N'bi-bank2', NULL, 22, N'SHCIL / e-stamping', 1, NULL);
    SET @ShcilID = SCOPE_IDENTITY();
END;

IF NOT EXISTS (SELECT 1 FROM dbo.MenuMaster WHERE MenuName = N'Stamp Activity' AND ParentMenuID = @ShcilID)
BEGIN
    INSERT INTO dbo.MenuMaster (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
    VALUES (@ShcilID, N'Stamp Activity', N'bi-file-earmark-ruled', N'/shcil/stamp-activity', 1,
            N'Uttarakhand e-Stamp manual entry and OCR', 1, NULL);
END
ELSE
BEGIN
    UPDATE dbo.MenuMaster
    SET MenuURL = N'/shcil/stamp-activity',
        MenuIcon = N'bi-file-earmark-ruled',
        Description = N'Uttarakhand e-Stamp manual entry and OCR',
        IsActive = 1
    WHERE MenuName = N'Stamp Activity' AND ParentMenuID = @ShcilID;
END;

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
