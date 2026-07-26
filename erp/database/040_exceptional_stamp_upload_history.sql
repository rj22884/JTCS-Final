USE JTCSS;
GO

IF OBJECT_ID(N'dbo.ExceptionalStampUploadCertificate', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ExceptionalStampUploadCertificate (
        UploadID            INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        CertificateNumber   NVARCHAR(100) NOT NULL,
        StampDutyAmount     INT NOT NULL
            CONSTRAINT DF_ExceptionalStampUploadCertificate_StampDutyAmount DEFAULT (0),
        SourceFileName      NVARCHAR(260) NULL,
        UploadedBy          NVARCHAR(150) NULL,
        UploadedDate        DATETIME2 NOT NULL
            CONSTRAINT DF_ExceptionalStampUploadCertificate_UploadedDate DEFAULT (SYSUTCDATETIME()),
        LastSeenDate        DATETIME2 NULL,
        CONSTRAINT UX_ExceptionalStampUploadCertificate_CertificateNumber
            UNIQUE (CertificateNumber)
    );
END;
GO

PRINT '040_exceptional_stamp_upload_history.sql completed.';
GO
