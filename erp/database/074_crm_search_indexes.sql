/*
    Search / performance indexes for CustomerMaster + CRM
*/
USE JTCSS;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_CustomerMaster_PANNumber' AND object_id = OBJECT_ID(N'dbo.CustomerMaster'))
    CREATE NONCLUSTERED INDEX IX_CustomerMaster_PANNumber ON dbo.CustomerMaster (PANNumber) WHERE PANNumber IS NOT NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_CustomerMaster_GSTNumber' AND object_id = OBJECT_ID(N'dbo.CustomerMaster'))
    CREATE NONCLUSTERED INDEX IX_CustomerMaster_GSTNumber ON dbo.CustomerMaster (GSTNumber) WHERE GSTNumber IS NOT NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_CustomerMaster_TANNumber' AND object_id = OBJECT_ID(N'dbo.CustomerMaster'))
    CREATE NONCLUSTERED INDEX IX_CustomerMaster_TANNumber ON dbo.CustomerMaster (TANNumber) WHERE TANNumber IS NOT NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_CustomerMaster_AadhaarNumber' AND object_id = OBJECT_ID(N'dbo.CustomerMaster'))
    CREATE NONCLUSTERED INDEX IX_CustomerMaster_AadhaarNumber ON dbo.CustomerMaster (AadhaarNumber) WHERE AadhaarNumber IS NOT NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_CustomerMaster_MobileNumber' AND object_id = OBJECT_ID(N'dbo.CustomerMaster'))
    CREATE NONCLUSTERED INDEX IX_CustomerMaster_MobileNumber ON dbo.CustomerMaster (MobileNumber) WHERE MobileNumber IS NOT NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_CustomerMaster_EmailID' AND object_id = OBJECT_ID(N'dbo.CustomerMaster'))
    CREATE NONCLUSTERED INDEX IX_CustomerMaster_EmailID ON dbo.CustomerMaster (EmailID) WHERE EmailID IS NOT NULL;
GO

PRINT '074_crm_search_indexes.sql completed.';
GO
