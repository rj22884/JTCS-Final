/*
    Followup modules — ITR, DSC, TDS, GST workflow + entries + menus
*/
USE JTCSS;
GO

IF OBJECT_ID(N'dbo.FollowupWorkflowStage', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.FollowupWorkflowStage (
        StageID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        ModuleCode NVARCHAR(10) NOT NULL,
        StageCode NVARCHAR(50) NOT NULL,
        StageName NVARCHAR(100) NOT NULL,
        DisplayOrder INT NOT NULL CONSTRAINT DF_FollowupWorkflowStage_DisplayOrder DEFAULT (1),
        ActiveStatus BIT NOT NULL CONSTRAINT DF_FollowupWorkflowStage_ActiveStatus DEFAULT (1),
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_FollowupWorkflowStage_CreatedDate DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT UX_FollowupWorkflowStage_ModuleCode UNIQUE (ModuleCode, StageCode)
    );
    CREATE INDEX IX_FollowupWorkflowStage_Module ON dbo.FollowupWorkflowStage (ModuleCode, ActiveStatus, DisplayOrder);
END;
GO

IF OBJECT_ID(N'dbo.FollowupEntryMaster', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.FollowupEntryMaster (
        EntryID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        ModuleCode NVARCHAR(10) NOT NULL,
        WorkDate DATE NOT NULL,
        TaxPeriod NVARCHAR(20) NOT NULL,
        CustomerID INT NOT NULL,
        ReturnType NVARCHAR(20) NULL,
        BillNo NVARCHAR(50) NULL,
        BillDate DATE NULL,
        PANNumber NVARCHAR(20) NULL,
        Remarks NVARCHAR(500) NULL,
        ReasonForUnverified NVARCHAR(500) NULL,
        CreatedBy NVARCHAR(100) NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_FollowupEntryMaster_CreatedDate DEFAULT (SYSUTCDATETIME()),
        ModifiedDate DATETIME2 NULL,
        IsActive BIT NOT NULL CONSTRAINT DF_FollowupEntryMaster_IsActive DEFAULT (1),
        CONSTRAINT FK_FollowupEntryMaster_Customer FOREIGN KEY (CustomerID) REFERENCES dbo.CustomerMaster (CustomerID)
    );
    CREATE INDEX IX_FollowupEntryMaster_ModuleDate ON dbo.FollowupEntryMaster (ModuleCode, WorkDate, IsActive);
END;
GO

IF OBJECT_ID(N'dbo.FollowupEntryStage', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.FollowupEntryStage (
        EntryStageID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        EntryID INT NOT NULL,
        StageID INT NOT NULL,
        CompletedDate DATETIME2 NOT NULL CONSTRAINT DF_FollowupEntryStage_CompletedDate DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT FK_FollowupEntryStage_Entry FOREIGN KEY (EntryID) REFERENCES dbo.FollowupEntryMaster (EntryID),
        CONSTRAINT FK_FollowupEntryStage_Stage FOREIGN KEY (StageID) REFERENCES dbo.FollowupWorkflowStage (StageID),
        CONSTRAINT UX_FollowupEntryStage UNIQUE (EntryID, StageID)
    );
END;
GO

/* ---- Seed workflow stages (idempotent) ---- */
MERGE dbo.FollowupWorkflowStage AS t
USING (
    VALUES
        (N'ITR', N'documents_received', N'Documents Received', 1),
        (N'ITR', N'itr_filed', N'ITR Filed', 2),
        (N'ITR', N'tally_bill_generated', N'Tally Bill Generated', 3),
        (N'ITR', N'payment_received', N'Payment Received', 4),
        (N'ITR', N'unverified', N'Unverified', 5),
        (N'DSC', N'documents_received', N'Documents Received', 1),
        (N'DSC', N'application_received', N'Application Received', 2),
        (N'DSC', N'kyc', N'KYC', 3),
        (N'DSC', N'download_status', N'Download Status', 4),
        (N'DSC', N'tally_bill_generated', N'Tally Bill Generated', 5),
        (N'DSC', N'payment_received', N'Payment Received', 6),
        (N'TDS', N'documents_received', N'Documents Received', 1),
        (N'TDS', N'kyc', N'KYC', 2),
        (N'TDS', N'tally_bill_generated', N'Tally Bill Generated', 3),
        (N'TDS', N'payment_received', N'Payment Received', 4),
        (N'GST', N'documents_received', N'Documents Received', 1),
        (N'GST', N'gstr1_filed', N'GSTR-1 Filed', 2),
        (N'GST', N'gstr3b_filed', N'GSTR-3B Filed', 3),
        (N'GST', N'tally_bill_generated', N'Tally Bill Generated', 4),
        (N'GST', N'payment_received', N'Payment Received', 5)
) AS s (ModuleCode, StageCode, StageName, DisplayOrder)
ON t.ModuleCode = s.ModuleCode AND t.StageCode = s.StageCode
WHEN NOT MATCHED THEN
    INSERT (ModuleCode, StageCode, StageName, DisplayOrder)
    VALUES (s.ModuleCode, s.StageCode, s.StageName, s.DisplayOrder)
WHEN MATCHED THEN
    UPDATE SET StageName = s.StageName, DisplayOrder = s.DisplayOrder, ActiveStatus = 1;
GO

/* ---- Activity menu URLs ---- */
DECLARE @ItrID INT = (SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'ITR' AND ParentMenuID IS NULL);
IF @ItrID IS NOT NULL
    UPDATE dbo.MenuMaster SET MenuURL = N'/itr/followup', IsActive = 1
    WHERE MenuName = N'ITR Followup' AND ParentMenuID = @ItrID;

DECLARE @DscID INT = (SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'DSC' AND ParentMenuID IS NULL);
IF @DscID IS NOT NULL
BEGIN
    IF EXISTS (SELECT 1 FROM dbo.MenuMaster WHERE MenuName = N'DSC Followup' AND ParentMenuID = @DscID)
        UPDATE dbo.MenuMaster SET MenuURL = N'/dsc/followup', MenuIcon = N'bi-list-check', IsActive = 1
        WHERE MenuName = N'DSC Followup' AND ParentMenuID = @DscID;
    ELSE
        INSERT INTO dbo.MenuMaster (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive)
        VALUES (@DscID, N'DSC Followup', N'bi-list-check', N'/dsc/followup', 0, N'DSC follow-up tracker', 1);
END;

DECLARE @TdsID INT = (SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'TDS' AND ParentMenuID IS NULL);
IF @TdsID IS NOT NULL
BEGIN
    IF EXISTS (SELECT 1 FROM dbo.MenuMaster WHERE MenuName = N'TDS Followup' AND ParentMenuID = @TdsID)
        UPDATE dbo.MenuMaster SET MenuURL = N'/tds/followup', MenuIcon = N'bi-list-check', IsActive = 1
        WHERE MenuName = N'TDS Followup' AND ParentMenuID = @TdsID;
    ELSE
        INSERT INTO dbo.MenuMaster (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive)
        VALUES (@TdsID, N'TDS Followup', N'bi-list-check', N'/tds/followup', 0, N'TDS follow-up tracker', 1);
END;

DECLARE @GstID INT = (SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'GST' AND ParentMenuID IS NULL);
IF @GstID IS NOT NULL
BEGIN
    IF EXISTS (SELECT 1 FROM dbo.MenuMaster WHERE MenuName = N'GST Followup' AND ParentMenuID = @GstID)
        UPDATE dbo.MenuMaster SET MenuURL = N'/gst/followup', MenuIcon = N'bi-list-check', IsActive = 1
        WHERE MenuName = N'GST Followup' AND ParentMenuID = @GstID;
    ELSE
        INSERT INTO dbo.MenuMaster (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive)
        VALUES (@GstID, N'GST Followup', N'bi-list-check', N'/gst/followup', 0, N'GST follow-up tracker', 1);
END;
GO

/* ---- Masters: followup workflow ---- */
DECLARE @MastersID INT = (SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'Masters' AND ParentMenuID IS NULL);

IF @MastersID IS NOT NULL
BEGIN
    IF NOT EXISTS (SELECT 1 FROM dbo.MenuMaster WHERE MenuName = N'ITR Followup Master' AND ParentMenuID = @MastersID)
        INSERT INTO dbo.MenuMaster (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive)
        VALUES (@MastersID, N'ITR Followup Master', N'bi-diagram-3', N'/masters/followup/itr', 20, N'ITR workflow stages master', 1);
    ELSE
        UPDATE dbo.MenuMaster SET MenuURL = N'/masters/followup/itr', IsActive = 1
        WHERE MenuName = N'ITR Followup Master' AND ParentMenuID = @MastersID;

    IF NOT EXISTS (SELECT 1 FROM dbo.MenuMaster WHERE MenuName = N'DSC Followup Master' AND ParentMenuID = @MastersID)
        INSERT INTO dbo.MenuMaster (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive)
        VALUES (@MastersID, N'DSC Followup Master', N'bi-diagram-3', N'/masters/followup/dsc', 21, N'DSC workflow stages master', 1);
    ELSE
        UPDATE dbo.MenuMaster SET MenuURL = N'/masters/followup/dsc', IsActive = 1
        WHERE MenuName = N'DSC Followup Master' AND ParentMenuID = @MastersID;

    IF NOT EXISTS (SELECT 1 FROM dbo.MenuMaster WHERE MenuName = N'TDS Followup Master' AND ParentMenuID = @MastersID)
        INSERT INTO dbo.MenuMaster (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive)
        VALUES (@MastersID, N'TDS Followup Master', N'bi-diagram-3', N'/masters/followup/tds', 22, N'TDS workflow stages master', 1);
    ELSE
        UPDATE dbo.MenuMaster SET MenuURL = N'/masters/followup/tds', IsActive = 1
        WHERE MenuName = N'TDS Followup Master' AND ParentMenuID = @MastersID;

    IF NOT EXISTS (SELECT 1 FROM dbo.MenuMaster WHERE MenuName = N'GST Followup Master' AND ParentMenuID = @MastersID)
        INSERT INTO dbo.MenuMaster (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive)
        VALUES (@MastersID, N'GST Followup Master', N'bi-diagram-3', N'/masters/followup/gst', 23, N'GST workflow stages master', 1);
    ELSE
        UPDATE dbo.MenuMaster SET MenuURL = N'/masters/followup/gst', IsActive = 1
        WHERE MenuName = N'GST Followup Master' AND ParentMenuID = @MastersID;
END;
GO

PRINT '030_followup_modules.sql completed.';
GO
