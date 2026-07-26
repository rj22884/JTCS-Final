/*
    Others menu — Income / Expense and Printing and Scanning module links
*/
USE JTCSS;
GO

DECLARE @OthersID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Others' AND ParentMenuID IS NULL
);

IF @OthersID IS NULL
BEGIN
    INSERT INTO dbo.MenuMaster (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
    VALUES (NULL, N'Others', N'bi-grid', NULL, 19, N'Other income and expense modules', 1, NULL);
    SET @OthersID = SCOPE_IDENTITY();
END
ELSE
BEGIN
    UPDATE dbo.MenuMaster
    SET MenuIcon = N'bi-grid',
        Description = N'Other income and expense modules',
        IsActive = 1
    WHERE MenuID = @OthersID;
END;
GO

DECLARE @OthersID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Others' AND ParentMenuID IS NULL
);

DECLARE @IncomeID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Income' AND ParentMenuID = @OthersID
);

IF @IncomeID IS NULL
BEGIN
    INSERT INTO dbo.MenuMaster (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
    VALUES (@OthersID, N'Income', N'bi-graph-up-arrow', NULL, 1, N'Other income services', 1, NULL);
    SET @IncomeID = SCOPE_IDENTITY();
END
ELSE
BEGIN
    UPDATE dbo.MenuMaster
    SET MenuIcon = N'bi-graph-up-arrow',
        MenuURL = NULL,
        DisplayOrder = 1,
        Description = N'Other income services',
        IsActive = 1
    WHERE MenuID = @IncomeID;
END;
GO

DECLARE @OthersID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Others' AND ParentMenuID IS NULL
);

IF NOT EXISTS (SELECT 1 FROM dbo.MenuMaster WHERE MenuName = N'Expense' AND ParentMenuID = @OthersID)
BEGIN
    INSERT INTO dbo.MenuMaster (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
    VALUES (@OthersID, N'Expense', N'bi-graph-down-arrow', NULL, 2, N'Other expense services', 1, NULL);
END
ELSE
BEGIN
    UPDATE dbo.MenuMaster
    SET MenuIcon = N'bi-graph-down-arrow',
        MenuURL = NULL,
        DisplayOrder = 2,
        Description = N'Other expense services',
        IsActive = 1
    WHERE MenuName = N'Expense' AND ParentMenuID = @OthersID;
END;
GO

DECLARE @OthersID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Others' AND ParentMenuID IS NULL
);
DECLARE @IncomeID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Income' AND ParentMenuID = @OthersID
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
        N'/others/income/printing-scanning',
        1,
        N'Printing and scanning income activity',
        1,
        NULL
    );
END
ELSE IF @IncomeID IS NOT NULL
BEGIN
    UPDATE dbo.MenuMaster
    SET MenuIcon = N'bi-printer',
        MenuURL = N'/others/income/printing-scanning',
        DisplayOrder = 1,
        Description = N'Printing and scanning income activity',
        IsActive = 1
    WHERE MenuName = N'Printing and Scanning' AND ParentMenuID = @IncomeID;
END;
GO

DECLARE @OthersID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Others' AND ParentMenuID IS NULL
);
DECLARE @IncomeID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Income' AND ParentMenuID = @OthersID
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
        N'/others/income/others',
        2,
        N'Other miscellaneous income',
        1,
        NULL
    );
END
ELSE IF @IncomeID IS NOT NULL
BEGIN
    UPDATE dbo.MenuMaster
    SET MenuIcon = N'bi-collection',
        MenuURL = N'/others/income/others',
        DisplayOrder = 2,
        Description = N'Other miscellaneous income',
        IsActive = 1
    WHERE MenuName = N'Others' AND ParentMenuID = @IncomeID;
END;
GO

PRINT '023_others_income_expense_menu.sql completed.';
GO
