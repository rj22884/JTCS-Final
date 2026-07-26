/*
    Masters menu — Income / Expense groups and Printing & Scanning work-type masters
*/
USE JTCSS;
GO

DECLARE @MastersID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Masters' AND ParentMenuID IS NULL
);

IF @MastersID IS NULL
BEGIN
    INSERT INTO dbo.MenuMaster (MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
    VALUES (N'Masters', N'bi-database', N'/masters', 5, N'Master data management', 1, NULL);
    SET @MastersID = SCOPE_IDENTITY();
END;
GO

DECLARE @MastersID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Masters' AND ParentMenuID IS NULL
);

-- Keep Bank Master first
UPDATE dbo.MenuMaster
SET DisplayOrder = 1,
    IsActive = 1
WHERE MenuName = N'Bank Master' AND ParentMenuID = @MastersID;
GO

DECLARE @MastersID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Masters' AND ParentMenuID IS NULL
);

DECLARE @IncomeID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Income' AND ParentMenuID = @MastersID
);

IF @IncomeID IS NULL
BEGIN
    INSERT INTO dbo.MenuMaster (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
    VALUES (@MastersID, N'Income', N'bi-graph-up-arrow', NULL, 2, N'Income master data', 1, NULL);
    SET @IncomeID = SCOPE_IDENTITY();
END
ELSE
BEGIN
    UPDATE dbo.MenuMaster
    SET MenuIcon = N'bi-graph-up-arrow',
        MenuURL = NULL,
        DisplayOrder = 2,
        Description = N'Income master data',
        IsActive = 1
    WHERE MenuID = @IncomeID;
END;
GO

DECLARE @MastersID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Masters' AND ParentMenuID IS NULL
);
DECLARE @IncomeID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Income' AND ParentMenuID = @MastersID
);

IF @IncomeID IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM dbo.MenuMaster
       WHERE MenuName = N'Printing and Scanning' AND ParentMenuID = @IncomeID
   )
BEGIN
    INSERT INTO dbo.MenuMaster (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
    VALUES (
        @IncomeID,
        N'Printing and Scanning',
        N'bi-printer',
        N'/masters/income/printing-scanning',
        1,
        N'Income printing & scanning work types',
        1,
        NULL
    );
END
ELSE IF @IncomeID IS NOT NULL
BEGIN
    UPDATE dbo.MenuMaster
    SET MenuIcon = N'bi-printer',
        MenuURL = N'/masters/income/printing-scanning',
        DisplayOrder = 1,
        Description = N'Income printing & scanning work types',
        IsActive = 1
    WHERE MenuName = N'Printing and Scanning' AND ParentMenuID = @IncomeID;
END;
GO

DECLARE @MastersID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Masters' AND ParentMenuID IS NULL
);
DECLARE @IncomeID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Income' AND ParentMenuID = @MastersID
);

IF @IncomeID IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM dbo.MenuMaster
       WHERE MenuName = N'Others' AND ParentMenuID = @IncomeID
   )
BEGIN
    INSERT INTO dbo.MenuMaster (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
    VALUES (
        @IncomeID,
        N'Others',
        N'bi-collection',
        N'/masters/income/others',
        2,
        N'Other income master data',
        1,
        NULL
    );
END
ELSE IF @IncomeID IS NOT NULL
BEGIN
    UPDATE dbo.MenuMaster
    SET MenuIcon = N'bi-collection',
        MenuURL = N'/masters/income/others',
        DisplayOrder = 2,
        Description = N'Other income master data',
        IsActive = 1
    WHERE MenuName = N'Others' AND ParentMenuID = @IncomeID;
END;
GO

DECLARE @MastersID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Masters' AND ParentMenuID IS NULL
);

DECLARE @ExpenseID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Expense' AND ParentMenuID = @MastersID
);

IF @ExpenseID IS NULL
BEGIN
    INSERT INTO dbo.MenuMaster (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
    VALUES (@MastersID, N'Expense', N'bi-graph-down-arrow', NULL, 3, N'Expense master data', 1, NULL);
    SET @ExpenseID = SCOPE_IDENTITY();
END
ELSE
BEGIN
    UPDATE dbo.MenuMaster
    SET MenuIcon = N'bi-graph-down-arrow',
        MenuURL = NULL,
        DisplayOrder = 3,
        Description = N'Expense master data',
        IsActive = 1
    WHERE MenuID = @ExpenseID;
END;
GO

DECLARE @MastersID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Masters' AND ParentMenuID IS NULL
);
DECLARE @ExpenseID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Expense' AND ParentMenuID = @MastersID
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
        N'/masters/expense/printing-scanning',
        1,
        N'Expense printing & scanning work types',
        1,
        NULL
    );
END
ELSE IF @ExpenseID IS NOT NULL
BEGIN
    UPDATE dbo.MenuMaster
    SET MenuIcon = N'bi-printer',
        MenuURL = N'/masters/expense/printing-scanning',
        DisplayOrder = 1,
        Description = N'Expense printing & scanning work types',
        IsActive = 1
    WHERE MenuName = N'Printing and Scanning' AND ParentMenuID = @ExpenseID;
END;
GO

DECLARE @MastersID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Masters' AND ParentMenuID IS NULL
);
DECLARE @ExpenseID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Expense' AND ParentMenuID = @MastersID
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
        N'/masters/expense/others',
        2,
        N'Other expense master data',
        1,
        NULL
    );
END
ELSE IF @ExpenseID IS NOT NULL
BEGIN
    UPDATE dbo.MenuMaster
    SET MenuIcon = N'bi-collection',
        MenuURL = N'/masters/expense/others',
        DisplayOrder = 2,
        Description = N'Other expense master data',
        IsActive = 1
    WHERE MenuName = N'Others' AND ParentMenuID = @ExpenseID;
END;
GO

PRINT '026_masters_income_expense_menu.sql completed.';
GO
