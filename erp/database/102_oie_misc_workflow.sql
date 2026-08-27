/*
    Others Income / Expense — Misc. workflow: Work Done → Tally Bill Generated → Payment
*/
USE JTCSS;
GO

IF COL_LENGTH(N'dbo.OthersIncomeExpenseMaster', N'CustomerID') IS NULL
    ALTER TABLE dbo.OthersIncomeExpenseMaster ADD CustomerID INT NULL;
GO

IF COL_LENGTH(N'dbo.OthersIncomeExpenseMaster', N'WorkDone') IS NULL
    ALTER TABLE dbo.OthersIncomeExpenseMaster ADD WorkDone BIT NOT NULL
        CONSTRAINT DF_OIE_WorkDone DEFAULT (0);
GO

IF COL_LENGTH(N'dbo.OthersIncomeExpenseMaster', N'TallyBillGenerated') IS NULL
    ALTER TABLE dbo.OthersIncomeExpenseMaster ADD TallyBillGenerated BIT NOT NULL
        CONSTRAINT DF_OIE_TallyBillGenerated DEFAULT (0);
GO

IF COL_LENGTH(N'dbo.OthersIncomeExpenseMaster', N'TallyBillNo') IS NULL
    ALTER TABLE dbo.OthersIncomeExpenseMaster ADD TallyBillNo NVARCHAR(50) NULL;
GO

IF COL_LENGTH(N'dbo.OthersIncomeExpenseMaster', N'TallyBillDate') IS NULL
    ALTER TABLE dbo.OthersIncomeExpenseMaster ADD TallyBillDate DATE NULL;
GO

IF COL_LENGTH(N'dbo.OthersIncomeExpenseMaster', N'TallyBillAmount') IS NULL
    ALTER TABLE dbo.OthersIncomeExpenseMaster ADD TallyBillAmount DECIMAL(18, 2) NULL;
GO

PRINT '102_oie_misc_workflow.sql completed.';
GO
