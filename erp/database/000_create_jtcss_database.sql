/*
    Create blank ERP database JTCSS on instance JTCS\JTCS.
    Does NOT modify the legacy JTCS database.
*/
IF NOT EXISTS (SELECT 1 FROM sys.databases WHERE name = N'JTCSS')
BEGIN
    CREATE DATABASE JTCSS;
    PRINT 'Database JTCSS created.';
END
ELSE
BEGIN
    PRINT 'Database JTCSS already exists.';
END
GO
