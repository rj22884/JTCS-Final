/*
    Create dbo.TransactionTypeMaster if missing (structure only).
    Earlier 015 bootstrap could not clone it when JTCS source table was absent on VPS.
    DATA safe — no row wipe; optional seed only when table is empty.
*/
USE JTCSS;
GO

IF OBJECT_ID(N'dbo.TransactionTypeMaster', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.TransactionTypeMaster (
        TransactionTypeID INT NOT NULL,
        TransactionTypeName NVARCHAR(50) NOT NULL,
        CONSTRAINT PK_TransactionTypeMaster PRIMARY KEY CLUSTERED (TransactionTypeID)
    );
    PRINT 'Created dbo.TransactionTypeMaster';
END
ELSE
BEGIN
    PRINT 'dbo.TransactionTypeMaster already exists';
END;
GO

IF OBJECT_ID(N'dbo.TransactionTypeMaster', N'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.key_constraints WHERE name = N'PK_TransactionTypeMaster')
BEGIN
    ALTER TABLE dbo.TransactionTypeMaster
    ADD CONSTRAINT PK_TransactionTypeMaster PRIMARY KEY CLUSTERED (TransactionTypeID);
END;
GO

/* Seed common types only when empty — never overwrite existing rows */
IF OBJECT_ID(N'dbo.TransactionTypeMaster', N'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM dbo.TransactionTypeMaster)
BEGIN
    INSERT INTO dbo.TransactionTypeMaster (TransactionTypeID, TransactionTypeName) VALUES
        (1, N'Cash'),
        (2, N'Bank'),
        (3, N'Income'),
        (4, N'Expense'),
        (5, N'Sales'),
        (6, N'Other');
    PRINT 'Seeded default TransactionTypeMaster rows';
END;
GO

PRINT '079_create_transaction_type_master.sql completed.';
GO
