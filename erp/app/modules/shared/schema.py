"""Idempotent CRM schema bootstrap (mirrors numbered SQL migrations)."""

from __future__ import annotations

from sqlalchemy import text

from app.extensions import db

_SCHEMA_READY = False

_STATEMENTS: tuple[str, ...] = (
    """
    IF COL_LENGTH(N'dbo.CustomerMaster', N'ModifiedDate') IS NULL
        ALTER TABLE dbo.CustomerMaster ADD ModifiedDate DATETIME2 NULL;
    """,
    """
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
            IsActive BIT NOT NULL CONSTRAINT DF_CrmLead_IsActive DEFAULT (1)
        );
        CREATE INDEX IX_CrmLead_Status ON dbo.CrmLead (Status, IsActive, CreatedDate DESC);
    END;
    """,
    """
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
            IsActive BIT NOT NULL CONSTRAINT DF_CrmConversation_IsActive DEFAULT (1)
        );
        CREATE INDEX IX_CrmConversation_Status ON dbo.CrmConversation (Status, IsActive, LastMessageAt DESC);
    END;
    """,
    """
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
            IsInternalNote BIT NOT NULL CONSTRAINT DF_CrmMessage_Internal DEFAULT (0)
        );
        CREATE INDEX IX_CrmMessage_Conversation ON dbo.CrmMessage (ConversationID, CreatedDate);
    END;
    """,
    """
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
            IsActive BIT NOT NULL CONSTRAINT DF_CrmTask_IsActive DEFAULT (1)
        );
        CREATE INDEX IX_CrmTask_Status ON dbo.CrmTask (Status, IsActive, Deadline);
    END;
    """,
    """
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
            IsActive BIT NOT NULL CONSTRAINT DF_CrmFollowUp_IsActive DEFAULT (1)
        );
        CREATE INDEX IX_CrmFollowUp_Due ON dbo.CrmFollowUp (Status, IsActive, DueAt);
    END;
    """,
    """
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
            CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_CrmTimelineEvent_CreatedDate DEFAULT (SYSUTCDATETIME())
        );
        CREATE INDEX IX_CrmTimelineEvent_Customer ON dbo.CrmTimelineEvent (CustomerID, CreatedDate DESC);
    END;
    """,
    """
    IF OBJECT_ID(N'dbo.Notification', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.Notification (
            NotificationID BIGINT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
            UserID INT NULL,
            NotificationType NVARCHAR(50) NOT NULL,
            Title NVARCHAR(255) NOT NULL,
            Message NVARCHAR(MAX) NULL,
            LinkURL NVARCHAR(500) NULL,
            Priority NVARCHAR(20) NOT NULL CONSTRAINT DF_Notification_Priority DEFAULT (N'Normal'),
            IsRead BIT NOT NULL CONSTRAINT DF_Notification_IsRead DEFAULT (0),
            IsArchived BIT NOT NULL CONSTRAINT DF_Notification_IsArchived DEFAULT (0),
            CustomerID INT NULL,
            LeadID INT NULL,
            EntityType NVARCHAR(50) NULL,
            EntityID INT NULL,
            CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_Notification_CreatedDate DEFAULT (SYSUTCDATETIME()),
            ReadDate DATETIME2 NULL
        );
        CREATE INDEX IX_Notification_UserUnread ON dbo.Notification (UserID, IsRead, IsArchived, CreatedDate DESC);
    END;
    """,
    """
    IF OBJECT_ID(N'dbo.AuditLog', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.AuditLog (
            AuditID BIGINT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
            UserID INT NULL,
            UserName NVARCHAR(150) NULL,
            ActionName NVARCHAR(100) NOT NULL,
            EntityType NVARCHAR(50) NULL,
            EntityID INT NULL,
            OldValue NVARCHAR(MAX) NULL,
            NewValue NVARCHAR(MAX) NULL,
            IPAddress NVARCHAR(64) NULL,
            Browser NVARCHAR(500) NULL,
            CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_AuditLog_CreatedDate DEFAULT (SYSUTCDATETIME())
        );
        CREATE INDEX IX_AuditLog_Created ON dbo.AuditLog (CreatedDate DESC);
    END;
    """,
    """
    IF OBJECT_ID(N'dbo.CrmDocument', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.CrmDocument (
            DocumentID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
            CustomerID INT NOT NULL,
            FolderType NVARCHAR(50) NOT NULL,
            Title NVARCHAR(255) NOT NULL,
            FileName NVARCHAR(255) NOT NULL,
            StoredPath NVARCHAR(500) NOT NULL,
            MimeType NVARCHAR(100) NULL,
            FileSizeBytes BIGINT NULL,
            CurrentVersion INT NOT NULL CONSTRAINT DF_CrmDocument_Version DEFAULT (1),
            Remarks NVARCHAR(500) NULL,
            UploadedByUserID INT NULL,
            UploadedByName NVARCHAR(150) NULL,
            CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_CrmDocument_CreatedDate DEFAULT (SYSUTCDATETIME()),
            ModifiedDate DATETIME2 NULL,
            IsActive BIT NOT NULL CONSTRAINT DF_CrmDocument_IsActive DEFAULT (1)
        );
        CREATE INDEX IX_CrmDocument_CustomerFolder ON dbo.CrmDocument (CustomerID, FolderType, IsActive);
    END;
    """,
    """
    IF OBJECT_ID(N'dbo.CrmDocumentVersion', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.CrmDocumentVersion (
            VersionID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
            DocumentID INT NOT NULL,
            VersionNumber INT NOT NULL,
            FileName NVARCHAR(255) NOT NULL,
            StoredPath NVARCHAR(500) NOT NULL,
            MimeType NVARCHAR(100) NULL,
            FileSizeBytes BIGINT NULL,
            UploadedByUserID INT NULL,
            UploadedByName NVARCHAR(150) NULL,
            CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_CrmDocumentVersion_CreatedDate DEFAULT (SYSUTCDATETIME())
        );
    END;
    """,
    """
    IF OBJECT_ID(N'dbo.CrmWorkflowDefinition', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.CrmWorkflowDefinition (
            DefinitionID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
            WorkflowCode NVARCHAR(50) NOT NULL,
            WorkflowName NVARCHAR(150) NOT NULL,
            Description NVARCHAR(500) NULL,
            IsActive BIT NOT NULL CONSTRAINT DF_CrmWorkflowDefinition_IsActive DEFAULT (1),
            CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_CrmWorkflowDefinition_CreatedDate DEFAULT (SYSUTCDATETIME())
        );
    END;
    """,
    """
    IF OBJECT_ID(N'dbo.CrmWorkflowStep', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.CrmWorkflowStep (
            StepID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
            DefinitionID INT NOT NULL,
            StepCode NVARCHAR(50) NOT NULL,
            StepName NVARCHAR(150) NOT NULL,
            DisplayOrder INT NOT NULL CONSTRAINT DF_CrmWorkflowStep_DisplayOrder DEFAULT (1),
            IsActive BIT NOT NULL CONSTRAINT DF_CrmWorkflowStep_IsActive DEFAULT (1)
        );
    END;
    """,
    """
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
            IsActive BIT NOT NULL CONSTRAINT DF_CrmWorkflowInstance_IsActive DEFAULT (1)
        );
    END;
    """,
    """
    IF OBJECT_ID(N'dbo.CrmWorkflowInstanceStep', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.CrmWorkflowInstanceStep (
            InstanceStepID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
            InstanceID INT NOT NULL,
            StepID INT NOT NULL,
            CompletedDate DATETIME2 NOT NULL CONSTRAINT DF_CrmWorkflowInstanceStep_Completed DEFAULT (SYSUTCDATETIME()),
            CompletedByUserID INT NULL,
            Notes NVARCHAR(500) NULL
        );
    END;
    """,
)


_MENU_ITEMS: tuple[tuple[str, str, str, int, str], ...] = (
    ("Dashboard", "bi-speedometer2", "/crm/dashboard", 1, "CRM dashboard"),
    ("Leads", "bi-person-plus", "/crm/leads", 2, "CRM leads"),
    ("Customer 360", "bi-person-bounding-box", "/crm/customer-360", 3, "Customer 360 view"),
    ("Communication Center", "bi-chat-dots", "/crm/inbox", 4, "CRM inbox"),
    ("Follow-up", "bi-telephone-outbound", "/crm/followups", 5, "CRM follow-ups"),
    ("Tasks", "bi-check2-square", "/crm/tasks", 6, "CRM tasks"),
    ("Timeline", "bi-clock-history", "/crm/timeline", 7, "Activity timeline"),
    ("Documents", "bi-folder2-open", "/crm/documents", 8, "Document vault"),
    ("Notifications", "bi-bell", "/crm/notifications", 9, "Notifications"),
    ("Workflow", "bi-diagram-3", "/crm/workflow", 10, "CRM workflow"),
    ("Calendar", "bi-calendar-event", "/crm/calendar", 11, "CRM calendar"),
    ("Analytics", "bi-graph-up", "/crm/analytics", 12, "CRM reports"),
    ("Audit Log", "bi-shield-check", "/crm/audit", 13, "CRM audit log"),
)


def ensure_crm_schema() -> None:
    """Create CRM tables if missing. Safe to call repeatedly."""
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    for stmt in _STATEMENTS:
        db.session.execute(text(stmt))
        db.session.commit()
    _seed_default_workflow()
    _SCHEMA_READY = True


def ensure_crm_menus() -> None:
    """Ensure CRM parent + child menus exist in MenuMaster."""
    row = db.session.execute(
        text(
            """
            SELECT TOP 1 MenuID FROM dbo.MenuMaster
            WHERE MenuName = N'CRM' AND ParentMenuID IS NULL
            """
        )
    ).first()
    if row:
        parent_id = int(row[0])
        db.session.execute(
            text(
                """
                UPDATE dbo.MenuMaster
                SET MenuIcon = N'bi-people', IsActive = 1,
                    Description = N'Customer Relationship Management'
                WHERE MenuID = :id
                """
            ),
            {"id": parent_id},
        )
    else:
        db.session.execute(
            text(
                """
                INSERT INTO dbo.MenuMaster
                    (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
                VALUES (NULL, N'CRM', N'bi-people', NULL, 25, N'Customer Relationship Management', 1, NULL)
                """
            )
        )
        db.session.commit()
        parent_id = int(
            db.session.execute(
                text(
                    """
                    SELECT TOP 1 MenuID FROM dbo.MenuMaster
                    WHERE MenuName = N'CRM' AND ParentMenuID IS NULL
                    """
                )
            ).scalar()
        )

    for name, icon, url, order, desc in _MENU_ITEMS:
        exists = db.session.execute(
            text(
                """
                SELECT TOP 1 MenuID FROM dbo.MenuMaster
                WHERE ParentMenuID = :parent AND MenuName = :name
                """
            ),
            {"parent": parent_id, "name": name},
        ).first()
        if exists:
            db.session.execute(
                text(
                    """
                    UPDATE dbo.MenuMaster
                    SET MenuIcon = :icon, MenuURL = :url, DisplayOrder = :ord,
                        Description = :desc, IsActive = 1
                    WHERE MenuID = :id
                    """
                ),
                {
                    "icon": icon,
                    "url": url,
                    "ord": order,
                    "desc": desc,
                    "id": int(exists[0]),
                },
            )
        else:
            db.session.execute(
                text(
                    """
                    INSERT INTO dbo.MenuMaster
                        (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
                    VALUES (:parent, :name, :icon, :url, :ord, :desc, 1, NULL)
                    """
                ),
                {
                    "parent": parent_id,
                    "name": name,
                    "icon": icon,
                    "url": url,
                    "ord": order,
                    "desc": desc,
                },
            )
    db.session.commit()


def _seed_default_workflow() -> None:
    exists = db.session.execute(
        text("SELECT TOP 1 DefinitionID FROM dbo.CrmWorkflowDefinition WHERE WorkflowCode = N'website_lead'")
    ).first()
    if exists:
        return
    db.session.execute(
        text(
            """
            INSERT INTO dbo.CrmWorkflowDefinition (WorkflowCode, WorkflowName, Description)
            VALUES (N'website_lead', N'Website Lead', N'Website lead to filing completed pipeline')
            """
        )
    )
    db.session.commit()
    def_id = db.session.execute(
        text("SELECT TOP 1 DefinitionID FROM dbo.CrmWorkflowDefinition WHERE WorkflowCode = N'website_lead'")
    ).scalar()
    steps = [
        ("assign_staff", "Assign Staff", 1),
        ("contact_customer", "Contact Customer", 2),
        ("collect_documents", "Collect Documents", 3),
        ("prepare_return", "Prepare Return", 4),
        ("review", "Review", 5),
        ("file", "File", 6),
        ("completed", "Completed", 7),
    ]
    for code, name, order in steps:
        db.session.execute(
            text(
                """
                INSERT INTO dbo.CrmWorkflowStep (DefinitionID, StepCode, StepName, DisplayOrder)
                VALUES (:def, :code, :name, :ord)
                """
            ),
            {"def": def_id, "code": code, "name": name, "ord": order},
        )
    db.session.commit()
