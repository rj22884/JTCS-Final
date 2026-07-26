/*
    Masters menu — replace Income + Expense with unified Income/Expense (WorkMaster)
*/
USE JTCSS;
GO

DECLARE @MastersID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Masters' AND ParentMenuID IS NULL
);

IF @MastersID IS NOT NULL
BEGIN
    DELETE child
    FROM dbo.MenuMaster AS child
    INNER JOIN dbo.MenuMaster AS parent ON child.ParentMenuID = parent.MenuID
    WHERE parent.ParentMenuID = @MastersID
      AND parent.MenuName IN (N'Income', N'Expense');

    DELETE FROM dbo.MenuMaster
    WHERE ParentMenuID = @MastersID
      AND MenuName IN (N'Income', N'Expense');
END;
GO

DECLARE @MastersID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Masters' AND ParentMenuID IS NULL
);

IF @MastersID IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM dbo.MenuMaster
       WHERE MenuName = N'Income/Expense' AND ParentMenuID = @MastersID
   )
BEGIN
    INSERT INTO dbo.MenuMaster (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
    VALUES (
        @MastersID,
        N'Income/Expense',
        N'bi-sliders',
        N'/masters/income-expense',
        2,
        N'Income and expense work type master (WorkMaster)',
        1,
        NULL
    );
END
ELSE IF @MastersID IS NOT NULL
BEGIN
    UPDATE dbo.MenuMaster
    SET MenuIcon = N'bi-sliders',
        MenuURL = N'/masters/income-expense',
        DisplayOrder = 2,
        Description = N'Income and expense work type master (WorkMaster)',
        IsActive = 1
    WHERE MenuName = N'Income/Expense' AND ParentMenuID = @MastersID;
END;
GO

PRINT '028_masters_income_expense_unified.sql completed.';
GO
