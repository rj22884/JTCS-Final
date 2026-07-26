/*
    Others — unified Income / Expense entry screen + menu link
*/
USE JTCSS;
GO

IF OBJECT_ID(N'dbo.OthersIncomeExpenseMaster', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.OthersIncomeExpenseMaster (
        EntryID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        BillNo NVARCHAR(50) NOT NULL,
        WorkDate DATE NOT NULL,
        WorkID INT NOT NULL,
        Amount DECIMAL(18, 2) NOT NULL,
        CustomerName NVARCHAR(255) NULL,
        MobileNumber NVARCHAR(15) NULL,
        Remarks NVARCHAR(500) NULL,
        CreatedBy NVARCHAR(100) NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_OthersIncomeExpenseMaster_CreatedDate DEFAULT (SYSUTCDATETIME()),
        IsActive BIT NOT NULL CONSTRAINT DF_OthersIncomeExpenseMaster_IsActive DEFAULT (1),
        CONSTRAINT FK_OthersIncomeExpenseMaster_Work FOREIGN KEY (WorkID) REFERENCES dbo.WorkMaster (WorkID),
        CONSTRAINT UX_OthersIncomeExpenseMaster_BillNo UNIQUE (BillNo)
    );
    CREATE INDEX IX_OthersIncomeExpenseMaster_WorkDate ON dbo.OthersIncomeExpenseMaster (WorkDate, WorkID);
END;
GO

DECLARE @OthersID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Others' AND ParentMenuID IS NULL
);

IF @OthersID IS NOT NULL
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM dbo.MenuMaster
        WHERE MenuName = N'Income / Expense' AND ParentMenuID = @OthersID
    )
    BEGIN
        INSERT INTO dbo.MenuMaster (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
        VALUES (
            @OthersID,
            N'Income / Expense',
            N'bi-cash-stack',
            N'/others/income-expense',
            0,
            N'Other income and expense entries',
            1,
            NULL
        );
    END
    ELSE
    BEGIN
        UPDATE dbo.MenuMaster
        SET MenuIcon = N'bi-cash-stack',
            MenuURL = N'/others/income-expense',
            DisplayOrder = 0,
            Description = N'Other income and expense entries',
            IsActive = 1
        WHERE MenuName = N'Income / Expense' AND ParentMenuID = @OthersID;
    END
END;
GO

PRINT '029_others_income_expense_entry.sql completed.';
GO
