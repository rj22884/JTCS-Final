/*
    Chart of Group Master — per-group Customer Master field ticks + custom fields.
    Values for custom fields are stored in CustomerDynFieldValue (EAV).
*/
SET NOCOUNT ON;

IF OBJECT_ID(N'dbo.DynMasterFieldDef', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.DynMasterFieldDef (
        FieldKey    NVARCHAR(80)  NOT NULL PRIMARY KEY,
        Label       NVARCHAR(150) NOT NULL,
        FieldType   NVARCHAR(20)  NOT NULL,
        Source      NVARCHAR(20)  NOT NULL
            CONSTRAINT DF_DynMasterFieldDef_Source DEFAULT (N'custom'),
        Hint        NVARCHAR(400) NULL,
        IsActive    BIT NOT NULL
            CONSTRAINT DF_DynMasterFieldDef_IsActive DEFAULT (1),
        CreatedDate DATETIME2 NOT NULL
            CONSTRAINT DF_DynMasterFieldDef_Created DEFAULT (SYSUTCDATETIME()),
        UpdatedDate DATETIME2 NULL
    );
END
GO

IF OBJECT_ID(N'dbo.DynMasterFieldGroupMap', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.DynMasterFieldGroupMap (
        GroupID      INT NOT NULL,
        FieldKey     NVARCHAR(80) NOT NULL,
        IsRequired   BIT NOT NULL
            CONSTRAINT DF_DynMasterFieldGroupMap_Req DEFAULT (0),
        DisplayOrder INT NOT NULL
            CONSTRAINT DF_DynMasterFieldGroupMap_Ord DEFAULT (100),
        CONSTRAINT PK_DynMasterFieldGroupMap PRIMARY KEY (GroupID, FieldKey)
    );
END
GO

IF OBJECT_ID(N'dbo.ChartOfGroupMaster', N'U') IS NOT NULL
   AND OBJECT_ID(N'dbo.DynMasterFieldGroupMap', N'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.foreign_keys
       WHERE name = N'FK_DynMasterFieldGroupMap_Group'
   )
    ALTER TABLE dbo.DynMasterFieldGroupMap
        ADD CONSTRAINT FK_DynMasterFieldGroupMap_Group
        FOREIGN KEY (GroupID) REFERENCES dbo.ChartOfGroupMaster (GroupID)
        ON DELETE CASCADE;
GO

IF OBJECT_ID(N'dbo.CustomerDynFieldValue', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.CustomerDynFieldValue (
        CustomerID INT NOT NULL,
        FieldKey   NVARCHAR(80) NOT NULL,
        FieldValue NVARCHAR(MAX) NULL,
        CONSTRAINT PK_CustomerDynFieldValue PRIMARY KEY (CustomerID, FieldKey)
    );
END
GO
