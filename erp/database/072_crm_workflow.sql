/*
    Configurable CRM workflow (separate from tax Followup* tables)
*/
USE JTCSS;
GO

IF OBJECT_ID(N'dbo.CrmWorkflowDefinition', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.CrmWorkflowDefinition (
        DefinitionID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        WorkflowCode NVARCHAR(50) NOT NULL,
        WorkflowName NVARCHAR(150) NOT NULL,
        Description NVARCHAR(500) NULL,
        IsActive BIT NOT NULL CONSTRAINT DF_CrmWorkflowDefinition_IsActive DEFAULT (1),
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_CrmWorkflowDefinition_CreatedDate DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT UX_CrmWorkflowDefinition_Code UNIQUE (WorkflowCode)
    );
END;
GO

IF OBJECT_ID(N'dbo.CrmWorkflowStep', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.CrmWorkflowStep (
        StepID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        DefinitionID INT NOT NULL,
        StepCode NVARCHAR(50) NOT NULL,
        StepName NVARCHAR(150) NOT NULL,
        DisplayOrder INT NOT NULL CONSTRAINT DF_CrmWorkflowStep_DisplayOrder DEFAULT (1),
        IsActive BIT NOT NULL CONSTRAINT DF_CrmWorkflowStep_IsActive DEFAULT (1),
        CONSTRAINT FK_CrmWorkflowStep_Definition FOREIGN KEY (DefinitionID) REFERENCES dbo.CrmWorkflowDefinition (DefinitionID),
        CONSTRAINT UX_CrmWorkflowStep UNIQUE (DefinitionID, StepCode)
    );
END;
GO

IF OBJECT_ID(N'dbo.CrmWorkflowInstance', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.CrmWorkflowInstance (
        InstanceID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        DefinitionID INT NOT NULL,
        CustomerID INT NULL,
        LeadID INT NULL,
        CurrentStepID INT NULL,
        Status NVARCHAR(30) NOT NULL CONSTRAINT DF_CrmWorkflowInstance_Status DEFAULT (N'InProgress'),
        AssignedUserID INT NULL,
        CreatedByUserID INT NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_CrmWorkflowInstance_CreatedDate DEFAULT (SYSUTCDATETIME()),
        ModifiedDate DATETIME2 NULL,
        CompletedDate DATETIME2 NULL,
        IsActive BIT NOT NULL CONSTRAINT DF_CrmWorkflowInstance_IsActive DEFAULT (1),
        CONSTRAINT FK_CrmWorkflowInstance_Definition FOREIGN KEY (DefinitionID) REFERENCES dbo.CrmWorkflowDefinition (DefinitionID),
        CONSTRAINT FK_CrmWorkflowInstance_Customer FOREIGN KEY (CustomerID) REFERENCES dbo.CustomerMaster (CustomerID)
    );
    CREATE INDEX IX_CrmWorkflowInstance_Status ON dbo.CrmWorkflowInstance (Status, IsActive);
END;
GO

IF OBJECT_ID(N'dbo.CrmWorkflowInstanceStep', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.CrmWorkflowInstanceStep (
        InstanceStepID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        InstanceID INT NOT NULL,
        StepID INT NOT NULL,
        CompletedDate DATETIME2 NOT NULL CONSTRAINT DF_CrmWorkflowInstanceStep_Completed DEFAULT (SYSUTCDATETIME()),
        CompletedByUserID INT NULL,
        Notes NVARCHAR(500) NULL,
        CONSTRAINT FK_CrmWorkflowInstanceStep_Instance FOREIGN KEY (InstanceID) REFERENCES dbo.CrmWorkflowInstance (InstanceID),
        CONSTRAINT FK_CrmWorkflowInstanceStep_Step FOREIGN KEY (StepID) REFERENCES dbo.CrmWorkflowStep (StepID),
        CONSTRAINT UX_CrmWorkflowInstanceStep UNIQUE (InstanceID, StepID)
    );
END;
GO

/* Default website-lead workflow */
IF NOT EXISTS (SELECT 1 FROM dbo.CrmWorkflowDefinition WHERE WorkflowCode = N'website_lead')
BEGIN
    INSERT INTO dbo.CrmWorkflowDefinition (WorkflowCode, WorkflowName, Description)
    VALUES (N'website_lead', N'Website Lead', N'Website lead to filing completed pipeline');

    DECLARE @DefID INT = SCOPE_IDENTITY();

    INSERT INTO dbo.CrmWorkflowStep (DefinitionID, StepCode, StepName, DisplayOrder)
    VALUES
        (@DefID, N'assign_staff', N'Assign Staff', 1),
        (@DefID, N'contact_customer', N'Contact Customer', 2),
        (@DefID, N'collect_documents', N'Collect Documents', 3),
        (@DefID, N'prepare_return', N'Prepare Return', 4),
        (@DefID, N'review', N'Review', 5),
        (@DefID, N'file', N'File', 6),
        (@DefID, N'completed', N'Completed', 7);
END;
GO

PRINT '072_crm_workflow.sql completed.';
GO
