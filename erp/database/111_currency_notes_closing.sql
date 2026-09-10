/*
    Daily currency-note count for Dashboard → Cash Closing Balance sub-card.
    Does not post to ledgers or change Cash Closing Balance.
*/
USE JTCSS;
GO

IF OBJECT_ID(N'dbo.CurrencyNotesClosing', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.CurrencyNotesClosing (
        EntryID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        EntryDate DATE NOT NULL,
        Note500 INT NOT NULL CONSTRAINT DF_CurrencyNotesClosing_Note500 DEFAULT (0),
        Note200 INT NOT NULL CONSTRAINT DF_CurrencyNotesClosing_Note200 DEFAULT (0),
        Note100 INT NOT NULL CONSTRAINT DF_CurrencyNotesClosing_Note100 DEFAULT (0),
        Note50 INT NOT NULL CONSTRAINT DF_CurrencyNotesClosing_Note50 DEFAULT (0),
        Note20 INT NOT NULL CONSTRAINT DF_CurrencyNotesClosing_Note20 DEFAULT (0),
        Note10 INT NOT NULL CONSTRAINT DF_CurrencyNotesClosing_Note10 DEFAULT (0),
        Note5 INT NOT NULL CONSTRAINT DF_CurrencyNotesClosing_Note5 DEFAULT (0),
        Note2 INT NOT NULL CONSTRAINT DF_CurrencyNotesClosing_Note2 DEFAULT (0),
        Note1 INT NOT NULL CONSTRAINT DF_CurrencyNotesClosing_Note1 DEFAULT (0),
        TotalNotes INT NOT NULL CONSTRAINT DF_CurrencyNotesClosing_TotalNotes DEFAULT (0),
        TotalAmount DECIMAL(18, 2) NOT NULL CONSTRAINT DF_CurrencyNotesClosing_TotalAmount DEFAULT (0),
        CreatedBy NVARCHAR(150) NULL,
        CreatedDate DATETIME2 NOT NULL
            CONSTRAINT DF_CurrencyNotesClosing_CreatedDate DEFAULT (SYSUTCDATETIME()),
        ModifiedBy NVARCHAR(150) NULL,
        ModifiedDate DATETIME2 NULL,
        IsActive BIT NOT NULL
            CONSTRAINT DF_CurrencyNotesClosing_IsActive DEFAULT (1)
    );
    CREATE UNIQUE INDEX UX_CurrencyNotesClosing_Date
        ON dbo.CurrencyNotesClosing (EntryDate)
        WHERE IsActive = 1;
END;
GO

PRINT '111_currency_notes_closing.sql completed.';
GO
