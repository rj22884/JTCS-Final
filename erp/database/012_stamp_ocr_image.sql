/*
    JTCS ERP - Stamp OCR image audit storage
*/
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = N'StampOcrImage')
BEGIN
    CREATE TABLE dbo.StampOcrImage (
        OcrImageID      INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        StampID         INT NULL,
        OriginalImage   VARBINARY(MAX) NULL,
        ImageHash       NVARCHAR(64) NULL,
        OcrText         NVARCHAR(MAX) NULL,
        OcrConfidence   DECIMAL(5, 2) NULL,
        OcrProvider     NVARCHAR(50) NULL,
        ImageSize       INT NULL,
        CreatedBy       NVARCHAR(150) NOT NULL,
        CreatedDate     DATETIME2 NOT NULL CONSTRAINT DF_StampOcrImage_CreatedDate DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT FK_StampOcrImage_Stamp FOREIGN KEY (StampID) REFERENCES dbo.StampMaster (StampID)
    );

    CREATE INDEX IX_StampOcrImage_StampID ON dbo.StampOcrImage (StampID);
    CREATE INDEX IX_StampOcrImage_ImageHash ON dbo.StampOcrImage (ImageHash);
END;
GO

PRINT '012_stamp_ocr_image.sql completed.';
GO
