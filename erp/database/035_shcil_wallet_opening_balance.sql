/*
    SHCIL Stamp Collection — manual wallet opening balance
*/
IF OBJECT_ID(N'dbo.ShcilWalletOpeningBalance', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ShcilWalletOpeningBalance (
        OpeningID           INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        AccountNumber       NVARCHAR(50) NOT NULL,
        OpeningBalance      DECIMAL(18, 2) NOT NULL
            CONSTRAINT DF_ShcilWalletOpeningBalance_OpeningBalance DEFAULT (0),
        OpeningBalanceDate  DATE NOT NULL,
        UpdatedBy           NVARCHAR(150) NOT NULL,
        UpdatedDate         DATETIME2 NOT NULL
            CONSTRAINT DF_ShcilWalletOpeningBalance_UpdatedDate DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT UX_ShcilWalletOpeningBalance_AccountNumber UNIQUE (AccountNumber)
    );
END
