/*
    CRM core — leads, conversations, messages, tasks, follow-ups, timeline
*/
USE JTCSS;
GO

IF COL_LENGTH(N'dbo.CustomerMaster', N'ModifiedDate') IS NULL
    ALTER TABLE dbo.CustomerMaster ADD ModifiedDate DATETIME2 NULL;
GO

IF OBJECT_ID(N'dbo.CrmLead', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.CrmLead (
        LeadID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        Source NVARCHAR(50) NOT NULL CONSTRAINT DF_CrmLead_Source DEFAULT (N'Website'),
        RequestType NVARCHAR(50) NOT NULL CONSTRAINT DF_CrmLead_RequestType DEFAULT (N'Contact'),
        FullName NVARCHAR(255) NOT NULL,
        Mobile NVARCHAR(20) NULL,
        Email NVARCHAR(255) NULL,
        BusinessName NVARCHAR(255) NULL,
        Message NVARCHAR(MAX) NULL,
        Status NVARCHAR(30) NOT NULL CONSTRAINT DF_CrmLead_Status DEFAULT (N'New'),
        Priority NVARCHAR(20) NOT NULL CONSTRAINT DF_CrmLead_Priority DEFAULT (N'Normal'),
        AssignedUserID INT NULL,
        CustomerID INT NULL,
        IdempotencyKey NVARCHAR(100) NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_CrmLead_CreatedDate DEFAULT (SYSUTCDATETIME()),
        ModifiedDate DATETIME2 NULL,
        IsActive BIT NOT NULL CONSTRAINT DF_CrmLead_IsActive DEFAULT (1),
        CONSTRAINT FK_CrmLead_Customer FOREIGN KEY (CustomerID) REFERENCES dbo.CustomerMaster (CustomerID)
    );
    CREATE INDEX IX_CrmLead_Status ON dbo.CrmLead (Status, IsActive, CreatedDate DESC);
    CREATE INDEX IX_CrmLead_Mobile ON dbo.CrmLead (Mobile);
    CREATE INDEX IX_CrmLead_Email ON dbo.CrmLead (Email);
    CREATE UNIQUE INDEX UX_CrmLead_IdempotencyKey ON dbo.CrmLead (IdempotencyKey) WHERE IdempotencyKey IS NOT NULL;
END;
GO

IF OBJECT_ID(N'dbo.CrmConversation', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.CrmConversation (
        ConversationID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        CustomerID INT NULL,
        LeadID INT NULL,
        Subject NVARCHAR(255) NULL,
        Channel NVARCHAR(50) NOT NULL CONSTRAINT DF_CrmConversation_Channel DEFAULT (N'Website'),
        Status NVARCHAR(30) NOT NULL CONSTRAINT DF_CrmConversation_Status DEFAULT (N'Open'),
        Priority NVARCHAR(20) NOT NULL CONSTRAINT DF_CrmConversation_Priority DEFAULT (N'Normal'),
        AssignedUserID INT NULL,
        LastMessageAt DATETIME2 NULL,
        UnreadCount INT NOT NULL CONSTRAINT DF_CrmConversation_Unread DEFAULT (0),
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_CrmConversation_CreatedDate DEFAULT (SYSUTCDATETIME()),
        ModifiedDate DATETIME2 NULL,
        IsActive BIT NOT NULL CONSTRAINT DF_CrmConversation_IsActive DEFAULT (1),
        CONSTRAINT FK_CrmConversation_Customer FOREIGN KEY (CustomerID) REFERENCES dbo.CustomerMaster (CustomerID),
        CONSTRAINT FK_CrmConversation_Lead FOREIGN KEY (LeadID) REFERENCES dbo.CrmLead (LeadID)
    );
    CREATE INDEX IX_CrmConversation_Status ON dbo.CrmConversation (Status, IsActive, LastMessageAt DESC);
    CREATE INDEX IX_CrmConversation_Customer ON dbo.CrmConversation (CustomerID, IsActive);
END;
GO

IF OBJECT_ID(N'dbo.CrmMessage', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.CrmMessage (
        MessageID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        ConversationID INT NOT NULL,
        Direction NVARCHAR(20) NOT NULL CONSTRAINT DF_CrmMessage_Direction DEFAULT (N'Inbound'),
        Channel NVARCHAR(50) NOT NULL,
        Body NVARCHAR(MAX) NULL,
        AttachmentPath NVARCHAR(500) NULL,
        AttachmentName NVARCHAR(255) NULL,
        CreatedByUserID INT NULL,
        CreatedByName NVARCHAR(150) NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_CrmMessage_CreatedDate DEFAULT (SYSUTCDATETIME()),
        IsInternalNote BIT NOT NULL CONSTRAINT DF_CrmMessage_Internal DEFAULT (0),
        CONSTRAINT FK_CrmMessage_Conversation FOREIGN KEY (ConversationID) REFERENCES dbo.CrmConversation (ConversationID)
    );
    CREATE INDEX IX_CrmMessage_Conversation ON dbo.CrmMessage (ConversationID, CreatedDate);
END;
GO

IF OBJECT_ID(N'dbo.CrmTask', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.CrmTask (
        TaskID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        CustomerID INT NULL,
        LeadID INT NULL,
        Title NVARCHAR(255) NOT NULL,
        Description NVARCHAR(MAX) NULL,
        Priority NVARCHAR(20) NOT NULL CONSTRAINT DF_CrmTask_Priority DEFAULT (N'Normal'),
        Status NVARCHAR(30) NOT NULL CONSTRAINT DF_CrmTask_Status DEFAULT (N'Pending'),
        Progress INT NOT NULL CONSTRAINT DF_CrmTask_Progress DEFAULT (0),
        Deadline DATETIME2 NULL,
        AssignedUserID INT NULL,
        AssignedUserName NVARCHAR(150) NULL,
        CreatedByUserID INT NULL,
        CreatedByName NVARCHAR(150) NULL,
        CompletedDate DATETIME2 NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_CrmTask_CreatedDate DEFAULT (SYSUTCDATETIME()),
        ModifiedDate DATETIME2 NULL,
        IsActive BIT NOT NULL CONSTRAINT DF_CrmTask_IsActive DEFAULT (1),
        CONSTRAINT FK_CrmTask_Customer FOREIGN KEY (CustomerID) REFERENCES dbo.CustomerMaster (CustomerID)
    );
    CREATE INDEX IX_CrmTask_Status ON dbo.CrmTask (Status, IsActive, Deadline);
    CREATE INDEX IX_CrmTask_Assigned ON dbo.CrmTask (AssignedUserID, Status);
END;
GO

IF OBJECT_ID(N'dbo.CrmFollowUp', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.CrmFollowUp (
        FollowUpID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        CustomerID INT NULL,
        LeadID INT NULL,
        FollowUpType NVARCHAR(30) NOT NULL,
        Subject NVARCHAR(255) NULL,
        Notes NVARCHAR(MAX) NULL,
        DueAt DATETIME2 NOT NULL,
        Status NVARCHAR(30) NOT NULL CONSTRAINT DF_CrmFollowUp_Status DEFAULT (N'Pending'),
        Priority NVARCHAR(20) NOT NULL CONSTRAINT DF_CrmFollowUp_Priority DEFAULT (N'Normal'),
        AssignedUserID INT NULL,
        AssignedUserName NVARCHAR(150) NULL,
        CompletedDate DATETIME2 NULL,
        CreatedByUserID INT NULL,
        CreatedByName NVARCHAR(150) NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_CrmFollowUp_CreatedDate DEFAULT (SYSUTCDATETIME()),
        ModifiedDate DATETIME2 NULL,
        IsActive BIT NOT NULL CONSTRAINT DF_CrmFollowUp_IsActive DEFAULT (1),
        CONSTRAINT FK_CrmFollowUp_Customer FOREIGN KEY (CustomerID) REFERENCES dbo.CustomerMaster (CustomerID)
    );
    CREATE INDEX IX_CrmFollowUp_Due ON dbo.CrmFollowUp (Status, IsActive, DueAt);
END;
GO

IF OBJECT_ID(N'dbo.CrmTimelineEvent', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.CrmTimelineEvent (
        EventID BIGINT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        CustomerID INT NULL,
        LeadID INT NULL,
        EventType NVARCHAR(50) NOT NULL,
        Title NVARCHAR(255) NOT NULL,
        Description NVARCHAR(MAX) NULL,
        EntityType NVARCHAR(50) NULL,
        EntityID INT NULL,
        CreatedByUserID INT NULL,
        CreatedByName NVARCHAR(150) NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_CrmTimelineEvent_CreatedDate DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT FK_CrmTimelineEvent_Customer FOREIGN KEY (CustomerID) REFERENCES dbo.CustomerMaster (CustomerID)
    );
    CREATE INDEX IX_CrmTimelineEvent_Customer ON dbo.CrmTimelineEvent (CustomerID, CreatedDate DESC);
    CREATE INDEX IX_CrmTimelineEvent_Lead ON dbo.CrmTimelineEvent (LeadID, CreatedDate DESC);
END;
GO

PRINT '069_crm_core.sql completed.';
GO
