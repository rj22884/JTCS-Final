/*
    Menu Management: optional per-menu text/background styling.
    Columns used by /admin/menus create & edit forms.
*/
SET NOCOUNT ON;

IF COL_LENGTH(N'dbo.MenuMaster', N'FontColor') IS NULL
BEGIN
    ALTER TABLE dbo.MenuMaster ADD FontColor NVARCHAR(20) NULL;
END;
GO

IF COL_LENGTH(N'dbo.MenuMaster', N'FontName') IS NULL
BEGIN
    ALTER TABLE dbo.MenuMaster ADD FontName NVARCHAR(100) NULL;
END;
GO

IF COL_LENGTH(N'dbo.MenuMaster', N'BackgroundColor') IS NULL
BEGIN
    ALTER TABLE dbo.MenuMaster ADD BackgroundColor NVARCHAR(20) NULL;
END;
GO
