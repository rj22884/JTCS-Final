/*
    JTCS ERP — Financial Statements foundation
    - ParentGroupID recursive hierarchy on ChartOfGroupMaster
    - GroupNature for BS / P&L classification
    - FixedAssetMaster for depreciation / schedule reports
*/
SET NOCOUNT ON;

IF OBJECT_ID(N'dbo.ChartOfGroupMaster', N'U') IS NOT NULL
BEGIN
    IF COL_LENGTH(N'dbo.ChartOfGroupMaster', N'ParentGroupID') IS NULL
        ALTER TABLE dbo.ChartOfGroupMaster ADD ParentGroupID INT NULL;

    IF COL_LENGTH(N'dbo.ChartOfGroupMaster', N'GroupNature') IS NULL
        ALTER TABLE dbo.ChartOfGroupMaster ADD GroupNature NVARCHAR(20) NULL;

    IF COL_LENGTH(N'dbo.ChartOfGroupMaster', N'ParentGroupID') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1 FROM sys.foreign_keys
           WHERE name = N'FK_ChartOfGroupMaster_Parent'
             AND parent_object_id = OBJECT_ID(N'dbo.ChartOfGroupMaster')
       )
        ALTER TABLE dbo.ChartOfGroupMaster
            ADD CONSTRAINT FK_ChartOfGroupMaster_Parent
            FOREIGN KEY (ParentGroupID) REFERENCES dbo.ChartOfGroupMaster (GroupID);
END
GO

IF OBJECT_ID(N'dbo.FixedAssetMaster', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.FixedAssetMaster (
        AssetID                 INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        AssetName               NVARCHAR(200) NOT NULL,
        AccountID               INT NULL,
        GroupID                 INT NULL,
        PurchaseDate            DATE NOT NULL,
        PurchaseValue           DECIMAL(18, 2) NOT NULL,
        DepreciationRate        DECIMAL(9, 4) NOT NULL CONSTRAINT DF_FixedAsset_Rate DEFAULT (0),
        OpeningAccumulatedDep   DECIMAL(18, 2) NOT NULL CONSTRAINT DF_FixedAsset_OpenAcc DEFAULT (0),
        CurrentYearDepreciation DECIMAL(18, 2) NOT NULL CONSTRAINT DF_FixedAsset_CYDep DEFAULT (0),
        AccumulatedDepreciation DECIMAL(18, 2) NOT NULL CONSTRAINT DF_FixedAsset_Acc DEFAULT (0),
        WDV                     DECIMAL(18, 2) NOT NULL CONSTRAINT DF_FixedAsset_WDV DEFAULT (0),
        Method                  NVARCHAR(20) NOT NULL CONSTRAINT DF_FixedAsset_Method DEFAULT (N'WDV'),
        IsActive                BIT NOT NULL CONSTRAINT DF_FixedAsset_Active DEFAULT (1),
        CreatedDate             DATETIME2 NOT NULL CONSTRAINT DF_FixedAsset_Created DEFAULT (SYSUTCDATETIME()),
        UpdatedDate             DATETIME2 NULL,
        CONSTRAINT CK_FixedAsset_Method CHECK (Method IN (N'WDV', N'SL'))
    );
    CREATE INDEX IX_FixedAssetMaster_GroupID ON dbo.FixedAssetMaster (GroupID);
    CREATE INDEX IX_FixedAssetMaster_AccountID ON dbo.FixedAssetMaster (AccountID);
END
GO
