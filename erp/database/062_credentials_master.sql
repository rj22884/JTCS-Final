/*
  062_credentials_master.sql
  Credentials Master table + Masters menu entry.
*/
SET NOCOUNT ON;

IF OBJECT_ID(N'dbo.CredentialsMaster', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.CredentialsMaster (
        CredentialID   INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_CredentialsMaster PRIMARY KEY,
        Activity       NVARCHAR(200) NOT NULL,
        URL            NVARCHAR(500) NULL,
        UserID         NVARCHAR(150) NULL,
        Password       NVARCHAR(200) NULL,
        EmailID        NVARCHAR(200) NULL,
        MobileNumber   NVARCHAR(20) NULL,
        ActiveStatus   BIT NOT NULL CONSTRAINT DF_CredentialsMaster_Active DEFAULT (1),
        CreatedBy      NVARCHAR(100) NULL,
        CreatedDate    DATETIME NOT NULL CONSTRAINT DF_CredentialsMaster_Created DEFAULT (GETUTCDATE()),
        ModifiedDate   DATETIME NULL
    );
    PRINT 'Created dbo.CredentialsMaster';
END
ELSE
    PRINT 'dbo.CredentialsMaster already exists';

DECLARE @MastersID INT;
SELECT TOP 1 @MastersID = MenuID
FROM dbo.MenuMaster
WHERE MenuName = N'Masters' AND ParentMenuID IS NULL
ORDER BY MenuID;

IF @MastersID IS NOT NULL
BEGIN
    IF EXISTS (
        SELECT 1 FROM dbo.MenuMaster
        WHERE ParentMenuID = @MastersID AND MenuName = N'Credentials Master'
    )
        UPDATE dbo.MenuMaster
        SET MenuURL = N'/masters/credentials',
            MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-key'),
            Description = N'Activity portal credentials vault',
            IsActive = 1
        WHERE ParentMenuID = @MastersID AND MenuName = N'Credentials Master';
    ELSE
        INSERT INTO dbo.MenuMaster (
            ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
            Description, IsActive, RoleName
        )
        VALUES (
            @MastersID, N'Credentials Master', N'bi-key', N'/masters/credentials',
            18, N'Activity portal credentials vault', 1, NULL
        );
END

PRINT '062_credentials_master.sql completed.';
