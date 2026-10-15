/*
    Masters → API Master (cloud email, WhatsApp, and other API credentials)
*/
USE JTCSS;
GO

DECLARE @MastersID INT = (
    SELECT TOP 1 MenuID
    FROM dbo.MenuMaster
    WHERE MenuName = N'Masters'
      AND ParentMenuID IS NULL
    ORDER BY MenuID
);

IF @MastersID IS NOT NULL
BEGIN
    IF EXISTS (
        SELECT 1
        FROM dbo.MenuMaster
        WHERE MenuURL = N'/masters/api-master'
           OR MenuName = N'API Master'
    )
        UPDATE dbo.MenuMaster
        SET ParentMenuID = @MastersID,
            MenuName = N'API Master',
            MenuURL = N'/masters/api-master',
            MenuIcon = N'bi-plugin',
            DisplayOrder = 4,
            Description = N'Cloud email, WhatsApp, SMS and other API credentials',
            IsActive = 1,
            RoleName = N'Administrator,Admin'
        WHERE MenuURL = N'/masters/api-master'
           OR MenuName = N'API Master';
    ELSE
        INSERT INTO dbo.MenuMaster (
            ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
            Description, IsActive, RoleName
        )
        VALUES (
            @MastersID,
            N'API Master',
            N'bi-plugin',
            N'/masters/api-master',
            4,
            N'Cloud email, WhatsApp, SMS and other API credentials',
            1,
            N'Administrator,Admin'
        );
END;
GO

PRINT '120_api_master_menu.sql completed.';
GO
