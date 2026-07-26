/*
    Remove Court Fee and Stamp menus (parent + children).
    Safe to run multiple times.
*/
SET NOCOUNT ON;

DELETE FROM dbo.MenuMaster
WHERE ParentMenuID IN (
    SELECT MenuID FROM dbo.MenuMaster WHERE MenuName IN (N'Court Fee', N'Stamp')
);

DELETE FROM dbo.MenuMaster
WHERE MenuName IN (N'Court Fee', N'Stamp');

GO
