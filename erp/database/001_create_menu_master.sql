/*
    JTCS ERP - MenuMaster table and initial navigation data
    Server: JTCS\JTCS
    Database: JTCSS
*/

IF NOT EXISTS (
    SELECT 1 FROM sys.tables WHERE name = N'MenuMaster' AND schema_id = SCHEMA_ID(N'dbo')
)
BEGIN
    CREATE TABLE dbo.MenuMaster (
        MenuID          INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        ParentMenuID    INT NULL,
        MenuName        NVARCHAR(100) NOT NULL,
        MenuIcon        NVARCHAR(100) NULL,
        MenuURL         NVARCHAR(250) NULL,
        DisplayOrder    INT NOT NULL CONSTRAINT DF_MenuMaster_DisplayOrder DEFAULT (0),
        IsActive        BIT NOT NULL CONSTRAINT DF_MenuMaster_IsActive DEFAULT (1),
        CreatedDate     DATETIME NOT NULL CONSTRAINT DF_MenuMaster_CreatedDate DEFAULT (GETDATE()),
        Description     NVARCHAR(300) NULL,
        RoleName        NVARCHAR(50) NULL,
        CONSTRAINT FK_MenuMaster_Parent FOREIGN KEY (ParentMenuID)
            REFERENCES dbo.MenuMaster (MenuID)
    );

    CREATE INDEX IX_MenuMaster_ParentMenuID ON dbo.MenuMaster (ParentMenuID);
    CREATE INDEX IX_MenuMaster_DisplayOrder ON dbo.MenuMaster (DisplayOrder);
    CREATE INDEX IX_MenuMaster_IsActive ON dbo.MenuMaster (IsActive);
    CREATE INDEX IX_MenuMaster_RoleName ON dbo.MenuMaster (RoleName);
END;
GO

IF NOT EXISTS (SELECT 1 FROM dbo.MenuMaster)
BEGIN
    SET IDENTITY_INSERT dbo.MenuMaster ON;

    INSERT INTO dbo.MenuMaster
        (MenuID, ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, IsActive, Description, RoleName)
    VALUES
        (1, NULL, N'Dashboard', N'bi-speedometer2', N'/dashboard', 1, 1, N'Main dashboard', NULL),
        (2, NULL, N'Data Entry', N'bi-pencil-square', N'/data-entry', 2, 1, N'Daily data entry workspace', NULL),
        (3, NULL, N'ITR', N'bi-file-earmark-text', NULL, 3, 1, N'Income Tax Return module', NULL),
        (4, NULL, N'Reports', N'bi-graph-up', N'/reports', 4, 1, N'Business reports', NULL),
        (5, NULL, N'Masters', N'bi-database', N'/masters', 5, 1, N'Master data management', NULL),
        (6, NULL, N'Settings', N'bi-gear', N'/settings', 6, 1, N'Application settings', N'Administrator'),
        (7, NULL, N'Administration', N'bi-shield-lock', N'/administration', 7, 1, N'Administration tools', N'Administrator'),
        (8, NULL, N'Logout', N'bi-box-arrow-right', N'/logout', 99, 1, N'Sign out of the application', NULL);

    INSERT INTO dbo.MenuMaster
        (MenuID, ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, IsActive, Description, RoleName)
    VALUES
        (9, 3, N'ITR Followup', N'bi-list-check', N'/itr/followup', 1, 1, N'Track ITR follow-up tasks', NULL),
        (10, 3, N'File Income Tax Return', N'bi-file-earmark-plus', N'/itr/file-return', 2, 1, N'File income tax returns', NULL),
        (11, 3, N'Sync Data with ITD', N'bi-cloud-arrow-down', N'/itr/sync-itd', 3, 1, N'Sync data with Income Tax Department', NULL),
        (12, 3, N'Sync Data Other Portal', N'bi-cloud-arrow-up', N'/itr/sync-other', 4, 1, N'Sync data with other portals', NULL);

    SET IDENTITY_INSERT dbo.MenuMaster OFF;
END;
GO
