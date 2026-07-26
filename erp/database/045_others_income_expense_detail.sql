/*
    Others Income / Expense — multi-category detail lines
*/
USE JTCSS;
GO

IF OBJECT_ID(N'dbo.OthersIncomeExpenseDetail', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.OthersIncomeExpenseDetail (
        DetailID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        EntryID INT NOT NULL,
        LineSequence INT NOT NULL,
        WorkID INT NOT NULL,
        Amount DECIMAL(18, 2) NOT NULL,
        CONSTRAINT FK_OthersIncomeExpenseDetail_Entry
            FOREIGN KEY (EntryID) REFERENCES dbo.OthersIncomeExpenseMaster (EntryID),
        CONSTRAINT FK_OthersIncomeExpenseDetail_Work
            FOREIGN KEY (WorkID) REFERENCES dbo.WorkMaster (WorkID),
        CONSTRAINT UX_OthersIncomeExpenseDetail_Entry_Seq UNIQUE (EntryID, LineSequence)
    );
    CREATE INDEX IX_OthersIncomeExpenseDetail_EntryID
        ON dbo.OthersIncomeExpenseDetail (EntryID);
END;
GO

-- Backfill one detail line per existing master row that has no details yet
IF OBJECT_ID(N'dbo.OthersIncomeExpenseDetail', N'U') IS NOT NULL
BEGIN
    INSERT INTO dbo.OthersIncomeExpenseDetail (EntryID, LineSequence, WorkID, Amount)
    SELECT m.EntryID, 1, m.WorkID, m.Amount
    FROM dbo.OthersIncomeExpenseMaster m
    WHERE NOT EXISTS (
        SELECT 1
        FROM dbo.OthersIncomeExpenseDetail d
        WHERE d.EntryID = m.EntryID
    );
END;
GO

PRINT '045_others_income_expense_detail.sql completed.';
GO
