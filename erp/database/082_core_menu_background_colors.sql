/*
    Sync core top-menu BackgroundColor values (local ERP look).
    DATA safe — MenuMaster.BackgroundColor only.
*/
USE JTCSS;
GO

IF COL_LENGTH(N'dbo.MenuMaster', N'BackgroundColor') IS NULL
    ALTER TABLE dbo.MenuMaster ADD BackgroundColor NVARCHAR(20) NULL;
GO

UPDATE dbo.MenuMaster SET BackgroundColor = N'#257B24'
WHERE ParentMenuID IS NULL AND MenuName = N'Dashboard';

UPDATE dbo.MenuMaster SET BackgroundColor = N'#247B25'
WHERE ParentMenuID IS NULL AND MenuName = N'Activities';

UPDATE dbo.MenuMaster SET BackgroundColor = N'#247B29'
WHERE ParentMenuID IS NULL AND MenuName = N'Reports and Analysis';

UPDATE dbo.MenuMaster SET BackgroundColor = N'#247B3E'
WHERE ParentMenuID IS NULL AND MenuName = N'Masters';
GO

PRINT '082_core_menu_background_colors.sql completed.';
GO
