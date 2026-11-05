/*
    Public Report → Ration Card Report → Ration Card Detail Report for FPS

    Ration dealer master + CSV upload history for FPS ration-card detail reports.
    DATA safe / idempotent.
*/
USE JTCSS;
GO

IF OBJECT_ID(N'dbo.RationDealerMaster', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.RationDealerMaster (
        DealerID            INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        DealerName          NVARCHAR(200) NOT NULL,
        FPSID               NVARCHAR(80) NULL,
        ExistingFPSID       NVARCHAR(80) NULL,
        DistrictName        NVARCHAR(120) NULL,
        TehsilName          NVARCHAR(120) NULL,
        MobileNumber        NVARCHAR(20) NULL,
        Address             NVARCHAR(400) NULL,
        ActiveStatus        BIT NOT NULL CONSTRAINT DF_RationDealerMaster_Active DEFAULT (1),
        CreatedBy           NVARCHAR(150) NULL,
        CreatedDate         DATETIME2 NOT NULL CONSTRAINT DF_RationDealerMaster_Created DEFAULT (SYSUTCDATETIME()),
        ModifiedBy          NVARCHAR(150) NULL,
        ModifiedDate        DATETIME2 NULL
    );

    CREATE UNIQUE INDEX UX_RationDealerMaster_DealerName
        ON dbo.RationDealerMaster (DealerName);

    CREATE UNIQUE INDEX UX_RationDealerMaster_FPSID
        ON dbo.RationDealerMaster (FPSID)
        WHERE FPSID IS NOT NULL AND FPSID <> N'';

    CREATE INDEX IX_RationDealerMaster_ExistingFPSID
        ON dbo.RationDealerMaster (ExistingFPSID);
END;
GO

IF OBJECT_ID(N'dbo.RationCardUploadBatch', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.RationCardUploadBatch (
        BatchID             INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        DealerID            INT NOT NULL,
        SourceFileName      NVARCHAR(260) NULL,
        FPSID               NVARCHAR(80) NULL,
        UploadedBy          NVARCHAR(150) NULL,
        UploadedDate        DATETIME2 NOT NULL CONSTRAINT DF_RationCardUploadBatch_Uploaded DEFAULT (SYSUTCDATETIME()),
        TotalRows           INT NOT NULL CONSTRAINT DF_RationCardUploadBatch_TotalRows DEFAULT (0),
        CardCount           INT NOT NULL CONSTRAINT DF_RationCardUploadBatch_CardCount DEFAULT (0),
        MemberCount         INT NOT NULL CONSTRAINT DF_RationCardUploadBatch_MemberCount DEFAULT (0),
        ImportMode          NVARCHAR(20) NULL,
        CONSTRAINT FK_RationCardUploadBatch_Dealer
            FOREIGN KEY (DealerID) REFERENCES dbo.RationDealerMaster (DealerID)
    );

    CREATE INDEX IX_RationCardUploadBatch_DealerID
        ON dbo.RationCardUploadBatch (DealerID, UploadedDate DESC);
END;
GO

IF OBJECT_ID(N'dbo.RationCardMember', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.RationCardMember (
        MemberRowID         INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        BatchID             INT NOT NULL,
        DealerID            INT NOT NULL,
        RowNumber           INT NOT NULL CONSTRAINT DF_RationCardMember_RowNumber DEFAULT (0),
        DistrictName        NVARCHAR(120) NULL,
        TehsilName          NVARCHAR(120) NULL,
        SchemeName          NVARCHAR(80) NULL,
        ExistingFPSID       NVARCHAR(80) NULL,
        FPSID               NVARCHAR(80) NULL,
        RCNumber            NVARCHAR(80) NULL,
        ExistingRCNumber    NVARCHAR(80) NULL,
        MemberID            NVARCHAR(80) NULL,
        ExistingMemberID    NVARCHAR(80) NULL,
        FullName            NVARCHAR(200) NULL,
        FatherName          NVARCHAR(200) NULL,
        MotherName          NVARCHAR(200) NULL,
        Gender              NVARCHAR(20) NULL,
        MobileNumber        NVARCHAR(30) NULL,
        Age                 INT NULL,
        IsHOF               BIT NOT NULL CONSTRAINT DF_RationCardMember_IsHOF DEFAULT (0),
        Ekyc                NVARCHAR(80) NULL,
        UIDStatus           NVARCHAR(80) NULL,
        ChangeStatus        NVARCHAR(20) NULL,
        ChangeDetail        NVARCHAR(800) NULL,
        CONSTRAINT FK_RationCardMember_Batch
            FOREIGN KEY (BatchID) REFERENCES dbo.RationCardUploadBatch (BatchID),
        CONSTRAINT FK_RationCardMember_Dealer
            FOREIGN KEY (DealerID) REFERENCES dbo.RationDealerMaster (DealerID)
    );

    CREATE INDEX IX_RationCardMember_BatchID ON dbo.RationCardMember (BatchID, RowNumber);
    CREATE INDEX IX_RationCardMember_Group
        ON dbo.RationCardMember (TehsilName, SchemeName, FPSID, RCNumber);
END;
GO

DECLARE @PublicID INT;
DECLARE @RationID INT;
DECLARE @CrmOrder INT = (
    SELECT TOP 1 DisplayOrder FROM dbo.MenuMaster
    WHERE MenuName = N'CRM' AND ParentMenuID IS NULL
    ORDER BY MenuID
);

SELECT TOP 1 @PublicID = MenuID
FROM dbo.MenuMaster
WHERE MenuName = N'Public Report' AND ParentMenuID IS NULL
ORDER BY MenuID;

IF @PublicID IS NULL
BEGIN
    INSERT INTO dbo.MenuMaster (
        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
        Description, IsActive, RoleName, BackgroundColor
    )
    VALUES (
        NULL, N'Public Report', N'bi-postcard', NULL, ISNULL(@CrmOrder, 25) + 1,
        N'Public distribution and citizen reports', 1, NULL, N'#0E7490'
    );
    SET @PublicID = SCOPE_IDENTITY();
END
ELSE
BEGIN
    UPDATE dbo.MenuMaster
    SET MenuIcon = N'bi-postcard',
        MenuURL = NULL,
        DisplayOrder = ISNULL(@CrmOrder, 25) + 1,
        Description = N'Public distribution and citizen reports',
        IsActive = 1,
        BackgroundColor = COALESCE(NULLIF(BackgroundColor, N''), N'#0E7490')
    WHERE MenuID = @PublicID;
END;

SELECT TOP 1 @RationID = MenuID
FROM dbo.MenuMaster
WHERE ParentMenuID = @PublicID AND MenuName = N'Ration Card Report'
ORDER BY MenuID;

IF @RationID IS NULL
BEGIN
    INSERT INTO dbo.MenuMaster (
        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
        Description, IsActive, RoleName
    )
    VALUES (
        @PublicID, N'Ration Card Report', N'bi-card-list', NULL, 1,
        N'Ration card reports for FPS dealers', 1, NULL
    );
    SET @RationID = SCOPE_IDENTITY();
END
ELSE
BEGIN
    UPDATE dbo.MenuMaster
    SET MenuIcon = N'bi-card-list',
        MenuURL = NULL,
        DisplayOrder = 1,
        Description = N'Ration card reports for FPS dealers',
        IsActive = 1
    WHERE MenuID = @RationID;
END;

IF EXISTS (
    SELECT 1 FROM dbo.MenuMaster
    WHERE MenuURL = N'/public-report/ration-card/fps-detail'
       OR (ParentMenuID = @RationID AND MenuName = N'Ration Card Detail Report for FPS')
)
    UPDATE dbo.MenuMaster
    SET ParentMenuID = @RationID,
        MenuName = N'Ration Card Detail Report for FPS',
        MenuIcon = N'bi-shop-window',
        MenuURL = N'/public-report/ration-card/fps-detail',
        DisplayOrder = 1,
        Description = N'FPS-wise ration card detail from NFSA CSV',
        IsActive = 1,
        RoleName = NULL
    WHERE MenuURL = N'/public-report/ration-card/fps-detail'
       OR (ParentMenuID = @RationID AND MenuName = N'Ration Card Detail Report for FPS');
ELSE
    INSERT INTO dbo.MenuMaster (
        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
        Description, IsActive, RoleName
    )
    VALUES (
        @RationID,
        N'Ration Card Detail Report for FPS',
        N'bi-shop-window',
        N'/public-report/ration-card/fps-detail',
        1,
        N'FPS-wise ration card detail from NFSA CSV',
        1,
        NULL
    );
GO

PRINT '112_ration_card_public_report.sql completed.';
GO
