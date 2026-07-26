/*
    Task 1: Others -> Expense — remove sub-menus; link Expense directly to activity.
    Task 3: Masters — flat sub-menu only (no Income/Expense nested groups).
    Does NOT change Others -> Income structure.
*/
USE JTCSS;
GO

/* ---- Others -> Expense: remove child menus, direct link ---- */
DECLARE @OthersID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Others' AND ParentMenuID IS NULL
);
DECLARE @OthersExpenseID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Expense' AND ParentMenuID = @OthersID
);

IF @OthersExpenseID IS NOT NULL
BEGIN
    DELETE FROM dbo.MenuMaster
    WHERE ParentMenuID = @OthersExpenseID;

    UPDATE dbo.MenuMaster
    SET MenuIcon = N'bi-graph-down-arrow',
        MenuURL = N'/others/expense/printing-scanning',
        DisplayOrder = 2,
        Description = N'Printing and scanning expense activity',
        IsActive = 1
    WHERE MenuID = @OthersExpenseID;
END;
GO

/* ---- Masters: remove nested sub-menus, flat Income / Expense links ---- */
DECLARE @MastersID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Masters' AND ParentMenuID IS NULL
);
DECLARE @MastersIncomeID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Income' AND ParentMenuID = @MastersID
);
DECLARE @MastersExpenseID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Expense' AND ParentMenuID = @MastersID
);

IF @MastersIncomeID IS NOT NULL
BEGIN
    DELETE FROM dbo.MenuMaster WHERE ParentMenuID = @MastersIncomeID;
    UPDATE dbo.MenuMaster
    SET MenuIcon = N'bi-graph-up-arrow',
        MenuURL = N'/masters/income',
        DisplayOrder = 2,
        Description = N'Income work type master (WorkMaster)',
        IsActive = 1
    WHERE MenuID = @MastersIncomeID;
END
ELSE IF @MastersID IS NOT NULL
BEGIN
    INSERT INTO dbo.MenuMaster (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
    VALUES (@MastersID, N'Income', N'bi-graph-up-arrow', N'/masters/income', 2, N'Income work type master (WorkMaster)', 1, NULL);
END;
GO

DECLARE @MastersID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Masters' AND ParentMenuID IS NULL
);
DECLARE @MastersExpenseID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Expense' AND ParentMenuID = @MastersID
);

IF @MastersExpenseID IS NOT NULL
BEGIN
    DELETE FROM dbo.MenuMaster WHERE ParentMenuID = @MastersExpenseID;
    UPDATE dbo.MenuMaster
    SET MenuIcon = N'bi-graph-down-arrow',
        MenuURL = N'/masters/expense',
        DisplayOrder = 3,
        Description = N'Expense work type master (WorkMaster)',
        IsActive = 1
    WHERE MenuID = @MastersExpenseID;
END
ELSE IF @MastersID IS NOT NULL
BEGIN
    INSERT INTO dbo.MenuMaster (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
    VALUES (@MastersID, N'Expense', N'bi-graph-down-arrow', N'/masters/expense', 3, N'Expense work type master (WorkMaster)', 1, NULL);
END;
GO

/* Remove stray nested Printing and Scanning / Others rows still under Masters */
DECLARE @MastersID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Masters' AND ParentMenuID IS NULL
);

DELETE child
FROM dbo.MenuMaster AS child
INNER JOIN dbo.MenuMaster AS parent ON child.ParentMenuID = parent.MenuID
WHERE parent.ParentMenuID = @MastersID
  AND parent.MenuName IN (N'Income', N'Expense')
  AND child.MenuName IN (N'Printing and Scanning', N'Others');
GO

PRINT '027_flatten_expense_masters_menu.sql completed.';
GO
