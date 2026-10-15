/*
    Menu Customization: allow all users, or selected users, per menu.
    DATA safe — MenuMaster column + MenuUserAllow only.
*/
USE JTCSS;
GO

IF COL_LENGTH(N'dbo.MenuMaster', N'AllowAllUsers') IS NULL
    ALTER TABLE dbo.MenuMaster ADD AllowAllUsers BIT NOT NULL
        CONSTRAINT DF_MenuMaster_AllowAllUsers DEFAULT (0);
GO

IF OBJECT_ID(N'dbo.MenuUserAllow', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.MenuUserAllow (
        MenuID INT NOT NULL,
        UserID INT NOT NULL,
        CONSTRAINT PK_MenuUserAllow PRIMARY KEY (MenuID, UserID),
        CONSTRAINT FK_MenuUserAllow_Menu FOREIGN KEY (MenuID)
            REFERENCES dbo.MenuMaster (MenuID)
    );
    CREATE INDEX IX_MenuUserAllow_UserID ON dbo.MenuUserAllow (UserID);
END;
GO

IF COL_LENGTH(N'dbo.MenuMaster', N'AllowAllUsers') IS NOT NULL
BEGIN
    UPDATE dbo.MenuMaster
    SET AllowAllUsers = 1,
        RoleName = NULL,
        IsActive = 1,
        MenuName = N'e-Stamp Orders',
        Description = N'Paid website e-Stamp purchase requests — all staff users'
    WHERE MenuURL = N'/admin/estamp-orders';
END;
GO

PRINT '117_menu_user_allow.sql completed.';
GO
