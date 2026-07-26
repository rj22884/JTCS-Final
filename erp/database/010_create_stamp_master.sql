/*
    JTCS ERP - StampMaster table and JTCSDailyTransaction.StampID link
*/
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = N'StampMaster')
BEGIN
    CREATE TABLE dbo.StampMaster (
        StampID                 INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        CertificateNumber       NVARCHAR(100) NOT NULL,
        CertificateIssuedDate   DATE NULL,
        AccountReference        NVARCHAR(200) NULL,
        UniqueDocumentReference NVARCHAR(200) NULL,
        PurchasedBy             NVARCHAR(300) NULL,
        DescriptionOfDocument   NVARCHAR(1000) NULL,
        PropertyDescription     NVARCHAR(1000) NULL,
        ConsiderationPrice      DECIMAL(18, 2) NULL,
        FirstPartyName          NVARCHAR(300) NULL,
        SecondPartyName         NVARCHAR(300) NULL,
        StampDutyPaidBy         NVARCHAR(300) NULL,
        StampDutyAmount         DECIMAL(18, 2) NULL,
        CreatedBy               NVARCHAR(150) NOT NULL,
        CreatedDate             DATETIME2 NOT NULL CONSTRAINT DF_StampMaster_CreatedDate DEFAULT (SYSUTCDATETIME()),
        ModifiedBy              NVARCHAR(150) NULL,
        ModifiedDate            DATETIME2 NULL,
        IsActive                BIT NOT NULL CONSTRAINT DF_StampMaster_IsActive DEFAULT (1),
        Remarks                 NVARCHAR(500) NULL,
        MachineName             NVARCHAR(100) NULL,
        IPAddress               NVARCHAR(45) NULL,
        CONSTRAINT UQ_StampMaster_CertificateNumber UNIQUE (CertificateNumber)
    );

    CREATE INDEX IX_StampMaster_CertificateIssuedDate ON dbo.StampMaster (CertificateIssuedDate);
    CREATE INDEX IX_StampMaster_IsActive ON dbo.StampMaster (IsActive);
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.JTCSDailyTransaction') AND name = N'StampID'
)
BEGIN
    ALTER TABLE dbo.JTCSDailyTransaction ADD StampID INT NULL;

    ALTER TABLE dbo.JTCSDailyTransaction
        ADD CONSTRAINT FK_JTCSDailyTransaction_Stamp
        FOREIGN KEY (StampID) REFERENCES dbo.StampMaster (StampID);

    CREATE INDEX IX_JTCSDailyTransaction_StampID ON dbo.JTCSDailyTransaction (StampID);
END;
GO

/* Ensure QR / UPI payment modes exist for stamp sales */
IF NOT EXISTS (SELECT 1 FROM dbo.PaymentModeMaster WHERE PaymentModeName = N'QR')
    INSERT INTO dbo.PaymentModeMaster (PaymentModeName, BankAccountID, IsActive) VALUES (N'QR', NULL, 1);

IF NOT EXISTS (SELECT 1 FROM dbo.PaymentModeMaster WHERE PaymentModeName = N'UPI')
    INSERT INTO dbo.PaymentModeMaster (PaymentModeName, BankAccountID, IsActive) VALUES (N'UPI', NULL, 1);

IF NOT EXISTS (SELECT 1 FROM dbo.PaymentModeMaster WHERE PaymentModeName = N'Cheque')
    INSERT INTO dbo.PaymentModeMaster (PaymentModeName, BankAccountID, IsActive) VALUES (N'Cheque', NULL, 1);
GO

PRINT '010_create_stamp_master.sql completed.';
GO
