/*
    JTCS ERP - Daily transaction table (all business work)
    Bank movements remain in existing JtcsBankTransaction only.
*/

IF NOT EXISTS (
    SELECT 1 FROM sys.tables WHERE name = N'JTCSDailyTransaction' AND schema_id = SCHEMA_ID(N'dbo')
)
BEGIN
    CREATE TABLE dbo.JTCSDailyTransaction (
        TransactionID       INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        TransactionDate     DATE NOT NULL,
        WorkType            NVARCHAR(50) NOT NULL,
        SubWorkType         NVARCHAR(100) NULL,
        CustomerID          INT NULL,
        CustomerName        NVARCHAR(200) NULL,
        ReferenceNo         NVARCHAR(100) NULL,
        Description         NVARCHAR(1000) NULL,
        IncomeAmount        DECIMAL(18, 2) NOT NULL CONSTRAINT DF_JTCSDailyTransaction_Income DEFAULT (0),
        ExpenseAmount       DECIMAL(18, 2) NOT NULL CONSTRAINT DF_JTCSDailyTransaction_Expense DEFAULT (0),
        SaleAmount          DECIMAL(18, 2) NOT NULL CONSTRAINT DF_JTCSDailyTransaction_Sale DEFAULT (0),
        PurchaseAmount      DECIMAL(18, 2) NOT NULL CONSTRAINT DF_JTCSDailyTransaction_Purchase DEFAULT (0),
        GSTAmount           DECIMAL(18, 2) NOT NULL CONSTRAINT DF_JTCSDailyTransaction_GST DEFAULT (0),
        TDSAmount           DECIMAL(18, 2) NOT NULL CONSTRAINT DF_JTCSDailyTransaction_TDS DEFAULT (0),
        Quantity            DECIMAL(18, 3) NULL,
        Rate                DECIMAL(18, 2) NULL,
        TotalAmount         DECIMAL(18, 2) NOT NULL CONSTRAINT DF_JTCSDailyTransaction_Total DEFAULT (0),
        BankTransactionID   INT NULL,
        PaymentModeID       INT NULL,
        Status              NVARCHAR(50) NOT NULL CONSTRAINT DF_JTCSDailyTransaction_Status DEFAULT (N'Posted'),
        CreatedBy           NVARCHAR(150) NOT NULL,
        CreatedDate         DATETIME2 NOT NULL CONSTRAINT DF_JTCSDailyTransaction_CreatedDate DEFAULT (SYSUTCDATETIME()),
        ModifiedDate        DATETIME2 NULL,
        Remarks             NVARCHAR(500) NULL,
        CONSTRAINT FK_JTCSDailyTransaction_Bank
            FOREIGN KEY (BankTransactionID) REFERENCES dbo.JtcsBankTransaction (JtcsBankTransactionID),
        CONSTRAINT FK_JTCSDailyTransaction_Customer
            FOREIGN KEY (CustomerID) REFERENCES dbo.CustomerMaster (CustomerID)
    );

    CREATE INDEX IX_JTCSDailyTransaction_Date ON dbo.JTCSDailyTransaction (TransactionDate);
    CREATE INDEX IX_JTCSDailyTransaction_WorkType ON dbo.JTCSDailyTransaction (WorkType, SubWorkType);
    CREATE INDEX IX_JTCSDailyTransaction_Customer ON dbo.JTCSDailyTransaction (CustomerID);
    CREATE INDEX IX_JTCSDailyTransaction_BankID ON dbo.JTCSDailyTransaction (BankTransactionID);
    CREATE INDEX IX_JTCSDailyTransaction_PaymentMode ON dbo.JTCSDailyTransaction (PaymentModeID);
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.tables WHERE name = N'PaymentModeMaster' AND schema_id = SCHEMA_ID(N'dbo')
)
BEGIN
    CREATE TABLE dbo.PaymentModeMaster (
        PaymentModeID       INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        PaymentModeName     NVARCHAR(100) NOT NULL,
        BankAccountID       INT NULL,
        IsActive            BIT NOT NULL CONSTRAINT DF_PaymentModeMaster_IsActive DEFAULT (1),
        CreatedDate         DATETIME2 NOT NULL CONSTRAINT DF_PaymentModeMaster_CreatedDate DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT FK_PaymentModeMaster_BankAccount
            FOREIGN KEY (BankAccountID) REFERENCES dbo.JtcsBankAccountMaster (JtcsBankAccountID)
    );
END;
GO

IF NOT EXISTS (SELECT 1 FROM dbo.PaymentModeMaster)
BEGIN
    INSERT INTO dbo.PaymentModeMaster (PaymentModeName, BankAccountID, IsActive)
    SELECT N'Cash', ba.JtcsBankAccountID, 1
    FROM dbo.JtcsBankAccountMaster ba
    WHERE ba.BankName = N'Cash'
      AND ba.ActiveStatus = 1;

    IF @@ROWCOUNT = 0
    BEGIN
        INSERT INTO dbo.PaymentModeMaster (PaymentModeName, BankAccountID, IsActive)
        VALUES (N'Cash', NULL, 1);
    END;

    INSERT INTO dbo.PaymentModeMaster (PaymentModeName, BankAccountID, IsActive)
    SELECT ba.BankName, ba.JtcsBankAccountID, ba.ActiveStatus
    FROM dbo.JtcsBankAccountMaster ba
    WHERE ba.ActiveStatus = 1
      AND ba.BankName <> N'Cash';
END;
GO
