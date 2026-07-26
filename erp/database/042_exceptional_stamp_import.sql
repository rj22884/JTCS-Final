USE JTCSS;
GO

IF OBJECT_ID(N'dbo.ExceptionalStampImport', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ExceptionalStampImport (
        ImportID            INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        BatchID             INT NULL,
        CertificateNumber   NVARCHAR(100) NOT NULL,
        StampDutyAmount     INT NOT NULL
            CONSTRAINT DF_ExceptionalStampImport_StampDutyAmount DEFAULT (0),
        StampDutyType       NVARCHAR(300) NULL,
        PaidBy              NVARCHAR(300) NULL,
        CertificateStatus   NVARCHAR(300) NULL,
        SourceFileName      NVARCHAR(260) NULL,
        ReportDateFrom      DATE NULL,
        ReportDateTo        DATE NULL,
        ImportedBy          NVARCHAR(150) NULL,
        ImportedDate        DATETIME2 NOT NULL
            CONSTRAINT DF_ExceptionalStampImport_ImportedDate DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT UX_ExceptionalStampImport_CertificateNumber
            UNIQUE (CertificateNumber)
    );

    IF OBJECT_ID(N'dbo.ExceptionalStampUploadBatch', N'U') IS NOT NULL
    BEGIN
        ALTER TABLE dbo.ExceptionalStampImport
            ADD CONSTRAINT FK_ExceptionalStampImport_Batch
            FOREIGN KEY (BatchID) REFERENCES dbo.ExceptionalStampUploadBatch(BatchID);
    END;
END;
GO

IF COL_LENGTH(N'dbo.ExceptionalStampImport', N'CertificateStatus') IS NULL
    ALTER TABLE dbo.ExceptionalStampImport ADD CertificateStatus NVARCHAR(300) NULL;
GO

PRINT '042_exceptional_stamp_import.sql completed.';
GO
