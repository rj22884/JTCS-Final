/*
    CRM document vault
*/
USE JTCSS;
GO

IF OBJECT_ID(N'dbo.CrmDocument', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.CrmDocument (
        DocumentID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        CustomerID INT NOT NULL,
        FolderType NVARCHAR(50) NOT NULL,
        Title NVARCHAR(255) NOT NULL,
        FileName NVARCHAR(255) NOT NULL,
        StoredPath NVARCHAR(500) NOT NULL,
        MimeType NVARCHAR(100) NULL,
        FileSizeBytes BIGINT NULL,
        CurrentVersion INT NOT NULL CONSTRAINT DF_CrmDocument_Version DEFAULT (1),
        Remarks NVARCHAR(500) NULL,
        UploadedByUserID INT NULL,
        UploadedByName NVARCHAR(150) NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_CrmDocument_CreatedDate DEFAULT (SYSUTCDATETIME()),
        ModifiedDate DATETIME2 NULL,
        IsActive BIT NOT NULL CONSTRAINT DF_CrmDocument_IsActive DEFAULT (1),
        CONSTRAINT FK_CrmDocument_Customer FOREIGN KEY (CustomerID) REFERENCES dbo.CustomerMaster (CustomerID)
    );
    CREATE INDEX IX_CrmDocument_CustomerFolder ON dbo.CrmDocument (CustomerID, FolderType, IsActive);
END;
GO

IF OBJECT_ID(N'dbo.CrmDocumentVersion', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.CrmDocumentVersion (
        VersionID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        DocumentID INT NOT NULL,
        VersionNumber INT NOT NULL,
        FileName NVARCHAR(255) NOT NULL,
        StoredPath NVARCHAR(500) NOT NULL,
        MimeType NVARCHAR(100) NULL,
        FileSizeBytes BIGINT NULL,
        UploadedByUserID INT NULL,
        UploadedByName NVARCHAR(150) NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_CrmDocumentVersion_CreatedDate DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT FK_CrmDocumentVersion_Document FOREIGN KEY (DocumentID) REFERENCES dbo.CrmDocument (DocumentID),
        CONSTRAINT UX_CrmDocumentVersion UNIQUE (DocumentID, VersionNumber)
    );
END;
GO

PRINT '071_documents.sql completed.';
GO
