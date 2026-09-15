/*
    Admin Role → Data Backup for Manager, Operator, and Viewer.
    Other Admin Role children stay as-is (nav still shows Data Backup only for those roles).
*/
USE JTCSS;
GO

DECLARE @ParentID INT;
DECLARE @DataBackupRoles NVARCHAR(80) = N'Administrator,Admin,Manager,Operator,Viewer';

SELECT TOP 1 @ParentID = MenuID
FROM dbo.MenuMaster
WHERE MenuName = N'Admin Role'
  AND ParentMenuID IS NULL
ORDER BY MenuID;

IF @ParentID IS NOT NULL
BEGIN
    UPDATE dbo.MenuMaster
    SET RoleName = @DataBackupRoles,
        IsActive = 1
    WHERE MenuID = @ParentID;

    UPDATE dbo.MenuMaster
    SET RoleName = @DataBackupRoles,
        IsActive = 1,
        MenuURL = COALESCE(NULLIF(MenuURL, N''), N'/admin/backup/data')
    WHERE ParentMenuID = @ParentID
      AND MenuName = N'Data Backup';

    UPDATE dbo.MenuMaster
    SET RoleName = @DataBackupRoles,
        IsActive = 1
    WHERE MenuURL = N'/admin/backup/data';
END;
GO

PRINT '109_data_backup_staff_roles.sql completed.';
GO
