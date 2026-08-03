/*
    Clone legacy base table STRUCTURES from JTCS into JTCSS (no data).
    Read-only against JTCS. All DDL applies only to JTCSS.

    Safe on VPS: if JTCS DB/table is missing, skip that table (no hard fail).
*/
USE JTCSS;
GO

DECLARE @tables TABLE (Name SYSNAME);
INSERT INTO @tables (Name) VALUES
    (N'Users'),
    (N'CustomerMaster'),
    (N'JtcsBankAccountMaster'),
    (N'JtcsBankTransaction'),
    (N'WorkTypeMaster'),
    (N'TransactionTypeMaster');

DECLARE @t SYSNAME;
DECLARE @sql NVARCHAR(MAX);
DECLARE c CURSOR LOCAL FAST_FORWARD FOR SELECT Name FROM @tables;
OPEN c;
FETCH NEXT FROM c INTO @t;
WHILE @@FETCH_STATUS = 0
BEGIN
    IF OBJECT_ID(N'dbo.' + @t, N'U') IS NULL
    BEGIN
        -- Skip cleanly when legacy JTCS source DB/table is not on this server.
        IF OBJECT_ID(N'JTCS.dbo.' + @t, N'U') IS NULL
        BEGIN
            PRINT 'Skip clone (source missing): ' + @t;
        END
        ELSE
        BEGIN
            BEGIN TRY
                SET @sql =
                    N'SELECT * INTO dbo.' + QUOTENAME(@t) +
                    N' FROM JTCS.dbo.' + QUOTENAME(@t) + N' WHERE 1 = 0;';
                EXEC sp_executesql @sql;
                PRINT 'Cloned structure: ' + @t;
            END TRY
            BEGIN CATCH
                PRINT 'Skip clone (error): ' + @t + N' — ' + ERROR_MESSAGE();
            END CATCH
        END
    END
    FETCH NEXT FROM c INTO @t;
END
CLOSE c;
DEALLOCATE c;
GO

IF OBJECT_ID(N'dbo.Users', N'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.key_constraints WHERE name = N'PK_Users')
    ALTER TABLE dbo.Users ADD CONSTRAINT PK_Users PRIMARY KEY CLUSTERED (UserID);
GO

IF OBJECT_ID(N'dbo.CustomerMaster', N'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.key_constraints WHERE name = N'PK_CustomerMaster')
    ALTER TABLE dbo.CustomerMaster ADD CONSTRAINT PK_CustomerMaster PRIMARY KEY CLUSTERED (CustomerID);
GO

IF OBJECT_ID(N'dbo.JtcsBankAccountMaster', N'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.key_constraints WHERE name = N'PK_JtcsBankAccountMaster')
    ALTER TABLE dbo.JtcsBankAccountMaster ADD CONSTRAINT PK_JtcsBankAccountMaster PRIMARY KEY CLUSTERED (JtcsBankAccountID);
GO

IF OBJECT_ID(N'dbo.JtcsBankTransaction', N'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.key_constraints WHERE name = N'PK_JtcsBankTransaction')
    ALTER TABLE dbo.JtcsBankTransaction ADD CONSTRAINT PK_JtcsBankTransaction PRIMARY KEY CLUSTERED (JtcsBankTransactionID);
GO

IF OBJECT_ID(N'dbo.WorkTypeMaster', N'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.key_constraints WHERE name = N'PK_WorkTypeMaster')
    ALTER TABLE dbo.WorkTypeMaster ADD CONSTRAINT PK_WorkTypeMaster PRIMARY KEY CLUSTERED (WorkTypeID);
GO

IF OBJECT_ID(N'dbo.TransactionTypeMaster', N'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.key_constraints WHERE name = N'PK_TransactionTypeMaster')
    ALTER TABLE dbo.TransactionTypeMaster ADD CONSTRAINT PK_TransactionTypeMaster PRIMARY KEY CLUSTERED (TransactionTypeID);
GO

PRINT '015_bootstrap_jtcss_legacy_structure.sql completed.';
GO
