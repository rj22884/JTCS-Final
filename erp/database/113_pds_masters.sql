/*
    Public Report → Ration Card Report masters

    State / District / DSO / ARO / SI / FPS / Ration Card.
    Uttarakhand geography is imported once by the app (Wikipedia or official fallback).
    DATA safe / idempotent.
*/
USE JTCSS;
GO

IF OBJECT_ID(N'dbo.PdsStateMaster', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.PdsStateMaster (
        StateID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        StateCode NVARCHAR(10) NOT NULL,
        StateName NVARCHAR(120) NOT NULL,
        Source NVARCHAR(80) NULL,
        ActiveStatus BIT NOT NULL CONSTRAINT DF_PdsStateMaster_Active DEFAULT (1),
        CreatedBy NVARCHAR(150) NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_PdsStateMaster_Created DEFAULT (SYSUTCDATETIME()),
        ModifiedBy NVARCHAR(150) NULL,
        ModifiedDate DATETIME2 NULL
    );
    CREATE UNIQUE INDEX UX_PdsStateMaster_StateCode ON dbo.PdsStateMaster (StateCode);
END;
GO

IF OBJECT_ID(N'dbo.PdsDistrictMaster', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.PdsDistrictMaster (
        DistrictID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        StateID INT NOT NULL,
        DistrictCode NVARCHAR(20) NOT NULL,
        DistrictName NVARCHAR(120) NOT NULL,
        Headquarters NVARCHAR(120) NULL,
        DivisionName NVARCHAR(80) NULL,
        Source NVARCHAR(80) NULL,
        ActiveStatus BIT NOT NULL CONSTRAINT DF_PdsDistrictMaster_Active DEFAULT (1),
        CreatedBy NVARCHAR(150) NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_PdsDistrictMaster_Created DEFAULT (SYSUTCDATETIME()),
        ModifiedBy NVARCHAR(150) NULL,
        ModifiedDate DATETIME2 NULL,
        CONSTRAINT FK_PdsDistrictMaster_State FOREIGN KEY (StateID) REFERENCES dbo.PdsStateMaster (StateID)
    );
    CREATE UNIQUE INDEX UX_PdsDistrictMaster_StateCode ON dbo.PdsDistrictMaster (StateID, DistrictCode);
    CREATE INDEX IX_PdsDistrictMaster_Name ON dbo.PdsDistrictMaster (DistrictName);
END;
GO

IF OBJECT_ID(N'dbo.PdsDsoMaster', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.PdsDsoMaster (
        DsoID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        DistrictID INT NOT NULL,
        DsoCode NVARCHAR(40) NOT NULL,
        DsoName NVARCHAR(200) NOT NULL,
        OfficerName NVARCHAR(200) NULL,
        MobileNumber NVARCHAR(20) NULL,
        Address NVARCHAR(400) NULL,
        Source NVARCHAR(80) NULL,
        ActiveStatus BIT NOT NULL CONSTRAINT DF_PdsDsoMaster_Active DEFAULT (1),
        CreatedBy NVARCHAR(150) NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_PdsDsoMaster_Created DEFAULT (SYSUTCDATETIME()),
        ModifiedBy NVARCHAR(150) NULL,
        ModifiedDate DATETIME2 NULL,
        CONSTRAINT FK_PdsDsoMaster_District FOREIGN KEY (DistrictID) REFERENCES dbo.PdsDistrictMaster (DistrictID)
    );
    CREATE UNIQUE INDEX UX_PdsDsoMaster_DistrictCode ON dbo.PdsDsoMaster (DistrictID, DsoCode);
END;
GO

IF OBJECT_ID(N'dbo.PdsAroMaster', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.PdsAroMaster (
        AroID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        DsoID INT NOT NULL,
        AroCode NVARCHAR(40) NOT NULL,
        AroName NVARCHAR(200) NOT NULL,
        OfficerName NVARCHAR(200) NULL,
        MobileNumber NVARCHAR(20) NULL,
        Address NVARCHAR(400) NULL,
        Source NVARCHAR(80) NULL,
        ActiveStatus BIT NOT NULL CONSTRAINT DF_PdsAroMaster_Active DEFAULT (1),
        CreatedBy NVARCHAR(150) NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_PdsAroMaster_Created DEFAULT (SYSUTCDATETIME()),
        ModifiedBy NVARCHAR(150) NULL,
        ModifiedDate DATETIME2 NULL,
        CONSTRAINT FK_PdsAroMaster_Dso FOREIGN KEY (DsoID) REFERENCES dbo.PdsDsoMaster (DsoID)
    );
    CREATE UNIQUE INDEX UX_PdsAroMaster_DsoCode ON dbo.PdsAroMaster (DsoID, AroCode);
END;
GO

IF OBJECT_ID(N'dbo.PdsSiMaster', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.PdsSiMaster (
        SiID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        AroID INT NOT NULL,
        SiCode NVARCHAR(40) NOT NULL,
        SiName NVARCHAR(200) NOT NULL,
        OfficerName NVARCHAR(200) NULL,
        MobileNumber NVARCHAR(20) NULL,
        Address NVARCHAR(400) NULL,
        Source NVARCHAR(80) NULL,
        ActiveStatus BIT NOT NULL CONSTRAINT DF_PdsSiMaster_Active DEFAULT (1),
        CreatedBy NVARCHAR(150) NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_PdsSiMaster_Created DEFAULT (SYSUTCDATETIME()),
        ModifiedBy NVARCHAR(150) NULL,
        ModifiedDate DATETIME2 NULL,
        CONSTRAINT FK_PdsSiMaster_Aro FOREIGN KEY (AroID) REFERENCES dbo.PdsAroMaster (AroID)
    );
    CREATE UNIQUE INDEX UX_PdsSiMaster_AroCode ON dbo.PdsSiMaster (AroID, SiCode);
END;
GO

IF OBJECT_ID(N'dbo.PdsFpsMaster', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.PdsFpsMaster (
        FpsRowID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        DistrictID INT NOT NULL,
        DsoID INT NULL,
        AroID INT NULL,
        SiID INT NULL,
        FpsCode NVARCHAR(80) NOT NULL,
        ExistingFpsId NVARCHAR(80) NULL,
        FpsName NVARCHAR(200) NOT NULL,
        DealerName NVARCHAR(200) NULL,
        TehsilName NVARCHAR(120) NULL,
        MobileNumber NVARCHAR(20) NULL,
        Address NVARCHAR(400) NULL,
        Source NVARCHAR(80) NULL,
        ActiveStatus BIT NOT NULL CONSTRAINT DF_PdsFpsMaster_Active DEFAULT (1),
        CreatedBy NVARCHAR(150) NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_PdsFpsMaster_Created DEFAULT (SYSUTCDATETIME()),
        ModifiedBy NVARCHAR(150) NULL,
        ModifiedDate DATETIME2 NULL,
        CONSTRAINT FK_PdsFpsMaster_District FOREIGN KEY (DistrictID) REFERENCES dbo.PdsDistrictMaster (DistrictID),
        CONSTRAINT FK_PdsFpsMaster_Dso FOREIGN KEY (DsoID) REFERENCES dbo.PdsDsoMaster (DsoID),
        CONSTRAINT FK_PdsFpsMaster_Aro FOREIGN KEY (AroID) REFERENCES dbo.PdsAroMaster (AroID),
        CONSTRAINT FK_PdsFpsMaster_Si FOREIGN KEY (SiID) REFERENCES dbo.PdsSiMaster (SiID)
    );
    CREATE UNIQUE INDEX UX_PdsFpsMaster_FpsCode ON dbo.PdsFpsMaster (FpsCode) WHERE FpsCode <> N'';
    CREATE INDEX IX_PdsFpsMaster_District ON dbo.PdsFpsMaster (DistrictID);
END;
GO

IF OBJECT_ID(N'dbo.PdsRationCardMaster', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.PdsRationCardMaster (
        CardID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        FpsRowID INT NOT NULL,
        RcNumber NVARCHAR(80) NOT NULL,
        ExistingRcNumber NVARCHAR(80) NULL,
        SchemeName NVARCHAR(80) NULL,
        HofName NVARCHAR(200) NULL,
        MemberCount INT NULL,
        MobileNumber NVARCHAR(20) NULL,
        Source NVARCHAR(80) NULL,
        ActiveStatus BIT NOT NULL CONSTRAINT DF_PdsRationCardMaster_Active DEFAULT (1),
        CreatedBy NVARCHAR(150) NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_PdsRationCardMaster_Created DEFAULT (SYSUTCDATETIME()),
        ModifiedBy NVARCHAR(150) NULL,
        ModifiedDate DATETIME2 NULL,
        CONSTRAINT FK_PdsRationCardMaster_Fps FOREIGN KEY (FpsRowID) REFERENCES dbo.PdsFpsMaster (FpsRowID)
    );
    CREATE UNIQUE INDEX UX_PdsRationCardMaster_FpsRc ON dbo.PdsRationCardMaster (FpsRowID, RcNumber) WHERE RcNumber <> N'';
    CREATE INDEX IX_PdsRationCardMaster_Fps ON dbo.PdsRationCardMaster (FpsRowID);
END;
GO

IF OBJECT_ID(N'dbo.PdsGeoImport', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.PdsGeoImport (
        ImportKey NVARCHAR(80) NOT NULL PRIMARY KEY,
        Source NVARCHAR(260) NULL,
        ImportRowCount INT NOT NULL CONSTRAINT DF_PdsGeoImport_RowCount DEFAULT (0),
        Detail NVARCHAR(500) NULL,
        ImportedDate DATETIME2 NOT NULL CONSTRAINT DF_PdsGeoImport_Imported DEFAULT (SYSUTCDATETIME())
    );
END;
GO
