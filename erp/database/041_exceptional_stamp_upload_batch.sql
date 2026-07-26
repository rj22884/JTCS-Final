USE JTCSS;
GO

IF OBJECT_ID(N'dbo.ExceptionalStampUploadBatch', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ExceptionalStampUploadBatch (
        BatchID             INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        SourceFileName      NVARCHAR(260) NULL,
        ReportDateFrom      DATE NULL,
        ReportDateTo        DATE NULL,
        UploadedBy          NVARCHAR(150) NULL,
        UploadedDate        DATETIME2 NOT NULL
            CONSTRAINT DF_ExceptionalStampUploadBatch_UploadedDate DEFAULT (SYSUTCDATETIME()),
        TotalRows           INT NOT NULL
            CONSTRAINT DF_ExceptionalStampUploadBatch_TotalRows DEFAULT (0),
        NewRows             INT NOT NULL
            CONSTRAINT DF_ExceptionalStampUploadBatch_NewRows DEFAULT (0),
        SkippedRows         INT NOT NULL
            CONSTRAINT DF_ExceptionalStampUploadBatch_SkippedRows DEFAULT (0)
    );
END;
GO

IF OBJECT_ID(N'dbo.ExceptionalStampUploadCertificate', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ExceptionalStampUploadCertificate (
        UploadID            INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        BatchID             INT NULL,
        CertificateNumber   NVARCHAR(100) NOT NULL,
        StampDutyAmount     INT NOT NULL
            CONSTRAINT DF_ExceptionalStampUploadCertificate_StampDutyAmount DEFAULT (0),
        StampDutyType       NVARCHAR(300) NULL,
        PaidBy              NVARCHAR(300) NULL,
        SourceFileName      NVARCHAR(260) NULL,
        ReportDateFrom      DATE NULL,
        ReportDateTo        DATE NULL,
        UploadedBy          NVARCHAR(150) NULL,
        UploadedDate        DATETIME2 NOT NULL
            CONSTRAINT DF_ExceptionalStampUploadCertificate_UploadedDate DEFAULT (SYSUTCDATETIME()),
        LastSeenDate        DATETIME2 NULL,
        CONSTRAINT UX_ExceptionalStampUploadCertificate_CertificateNumber
            UNIQUE (CertificateNumber)
    );
END;
GO

IF COL_LENGTH(N'dbo.ExceptionalStampUploadCertificate', N'BatchID') IS NULL
    ALTER TABLE dbo.ExceptionalStampUploadCertificate ADD BatchID INT NULL;
IF COL_LENGTH(N'dbo.ExceptionalStampUploadCertificate', N'ReportDateFrom') IS NULL
    ALTER TABLE dbo.ExceptionalStampUploadCertificate ADD ReportDateFrom DATE NULL;
IF COL_LENGTH(N'dbo.ExceptionalStampUploadCertificate', N'ReportDateTo') IS NULL
    ALTER TABLE dbo.ExceptionalStampUploadCertificate ADD ReportDateTo DATE NULL;
IF COL_LENGTH(N'dbo.ExceptionalStampUploadCertificate', N'StampDutyType') IS NULL
    ALTER TABLE dbo.ExceptionalStampUploadCertificate ADD StampDutyType NVARCHAR(300) NULL;
IF COL_LENGTH(N'dbo.ExceptionalStampUploadCertificate', N'PaidBy') IS NULL
    ALTER TABLE dbo.ExceptionalStampUploadCertificate ADD PaidBy NVARCHAR(300) NULL;
GO

PRINT '041_exceptional_stamp_upload_batch.sql completed.';
GO
