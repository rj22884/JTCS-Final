/*

    Widen role columns to store comma-separated multi-role values.

*/

USE JTCSS;

GO



IF EXISTS (

    SELECT 1 FROM sys.columns

    WHERE object_id = OBJECT_ID(N'dbo.Users') AND name = N'Role'

)

BEGIN

    ALTER TABLE dbo.Users ALTER COLUMN Role NVARCHAR(200) NOT NULL;

END;

GO



IF EXISTS (

    SELECT 1 FROM sys.columns

    WHERE object_id = OBJECT_ID(N'dbo.MenuMaster') AND name = N'RoleName'

)

BEGIN

    ALTER TABLE dbo.MenuMaster ALTER COLUMN RoleName NVARCHAR(200) NULL;

END;

GO



PRINT '054_multi_role_columns.sql completed.';

GO

