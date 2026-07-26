/*
    Others menu — Expense sub-modules (Printing and Scanning, Others)
*/
USE JTCSS;
GO

DECLARE @OthersID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Others' AND ParentMenuID IS NULL
);
DECLARE @ExpenseID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Expense' AND ParentMenuID = @OthersID
);

IF @ExpenseID IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM dbo.MenuMaster
       WHERE MenuName = N'Printing and Scanning' AND ParentMenuID = @ExpenseID
   )
BEGIN
    INSERT INTO dbo.MenuMaster (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
    VALUES (
        @ExpenseID,
        N'Printing and Scanning',
        N'bi-printer',
        N'/others/expense/printing-scanning',
        1,
        N'Printing and scanning expense activity',
        1,
        NULL
    );
END
ELSE IF @ExpenseID IS NOT NULL
BEGIN
    UPDATE dbo.MenuMaster
    SET MenuIcon = N'bi-printer',
        MenuURL = N'/others/expense/printing-scanning',
        DisplayOrder = 1,
        Description = N'Printing and scanning expense activity',
        IsActive = 1
    WHERE MenuName = N'Printing and Scanning' AND ParentMenuID = @ExpenseID;
END;
GO

DECLARE @OthersID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Others' AND ParentMenuID IS NULL
);
DECLARE @ExpenseID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Expense' AND ParentMenuID = @OthersID
);

IF @ExpenseID IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM dbo.MenuMaster
       WHERE MenuName = N'Others' AND ParentMenuID = @ExpenseID
   )
BEGIN
    INSERT INTO dbo.MenuMaster (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
    VALUES (
        @ExpenseID,
        N'Others',
        N'bi-collection',
        N'/others/expense/others',
        2,
        N'Other miscellaneous expense',
        1,
        NULL
    );
END
ELSE IF @ExpenseID IS NOT NULL
BEGIN
    UPDATE dbo.MenuMaster
    SET MenuIcon = N'bi-collection',
        MenuURL = N'/others/expense/others',
        DisplayOrder = 2,
        Description = N'Other miscellaneous expense',
        IsActive = 1
    WHERE MenuName = N'Others' AND ParentMenuID = @ExpenseID;
END;
GO

-- Fix any menu rows that accidentally stored a literal "None" URL
UPDATE dbo.MenuMaster
SET MenuURL = NULL
WHERE MenuURL IN (N'None', N'/others/income/None', N'/others/expense/None');
GO

IF NOT EXISTS (
    SELECT 1 FROM dbo.WorkMaster
    WHERE WorkName = N'Photostat' AND LedgerKind = N'Expense'
)
    INSERT INTO dbo.WorkMaster (WorkName, LedgerKind) VALUES (N'Photostat', N'Expense');

IF NOT EXISTS (
    SELECT 1 FROM dbo.WorkMaster
    WHERE WorkName = N'Print & Scan' AND LedgerKind = N'Expense'
)
    INSERT INTO dbo.WorkMaster (WorkName, LedgerKind) VALUES (N'Print & Scan', N'Expense');
GO

PRINT '025_others_expense_menu.sql completed.';
GO
