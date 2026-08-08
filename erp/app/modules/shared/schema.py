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


# Top-level CRM children (Communication Center is a folder; channels seeded separately).
_MENU_ITEMS: tuple[tuple[str, str, str | None, int, str], ...] = (
    ("Dashboard", "bi-speedometer2", "/crm/dashboard", 1, "CRM dashboard"),
    ("Communication Center", "bi-chat-dots", None, 2, "Unified multi-channel inbox"),
    ("Customer Master", "bi-people", "/masters/customer", 3, "Customer Master (Masters)"),
    ("Leads", "bi-person-plus", "/crm/leads", 4, "CRM leads"),
    ("Opportunities", "bi-bullseye", "/crm/opportunities", 5, "Opportunities (Phase 2)"),
    ("Tasks", "bi-check2-square", "/crm/tasks", 6, "CRM tasks"),
    ("Customer 360", "bi-person-bounding-box", "/crm/customer-360", 7, "Customer 360 view"),
    ("Follow-up Manager", "bi-telephone-outbound", "/crm/followups", 8, "CRM follow-ups"),
    ("Timeline", "bi-clock-history", "/crm/timeline", 9, "Activity timeline"),
    ("Documents", "bi-folder2-open", "/crm/documents", 10, "Document vault"),
    ("Notifications", "bi-bell", "/crm/notifications", 11, "Notifications"),
    ("Workflow", "bi-diagram-3", "/crm/workflow", 12, "CRM workflow"),
    ("Calendar", "bi-calendar-event", "/crm/calendar", 13, "CRM calendar"),
    ("Analytics", "bi-graph-up", "/crm/analytics", 14, "CRM reports"),
    ("Audit Log", "bi-shield-check", "/crm/audit", 15, "CRM audit log"),
)

_COMM_CENTER_CHILDREN: tuple[tuple[str, str, str, int, str], ...] = (
    ("WhatsApp Inbox", "bi-whatsapp", "/crm/inbox?channel=WhatsApp", 1, "WhatsApp conversations"),
    ("Email Inbox", "bi-envelope", "/crm/inbox?channel=Email", 2, "Email conversations"),
    ("SMS Inbox", "bi-chat-square-text", "/crm/inbox?channel=SMS", 3, "SMS inbox (Phase 2)"),
    ("Website Contact Messages", "bi-globe", "/crm/inbox?channel=Website", 4, "Website enquiries"),
    ("AI Chatbot Conversations", "bi-robot", "/crm/inbox?channel=AI", 5, "AI chatbot (Phase 2)"),
    ("Call Logs", "bi-telephone", "/crm/call-logs", 6, "Phone call logs"),
    ("Follow-up Manager", "bi-alarm", "/crm/followups", 7, "Pending and overdue follow-ups"),
    ("Customer Timeline", "bi-clock-history", "/crm/timeline", 8, "Customer activity timeline"),
)


_COMM_CENTER_ALTERS: tuple[str, ...] = (
    """
    IF COL_LENGTH(N'dbo.CrmConversation', N'ExternalThreadKey') IS NULL
        ALTER TABLE dbo.CrmConversation ADD ExternalThreadKey NVARCHAR(128) NULL;
    """,
    """
    IF COL_LENGTH(N'dbo.CrmConversation', N'ContactMobile') IS NULL
        ALTER TABLE dbo.CrmConversation ADD ContactMobile NVARCHAR(30) NULL;
    """,
    """
    IF COL_LENGTH(N'dbo.CrmConversation', N'ContactEmail') IS NULL
        ALTER TABLE dbo.CrmConversation ADD ContactEmail NVARCHAR(255) NULL;
    """,
    """
    IF COL_LENGTH(N'dbo.CrmConversation', N'IsPinned') IS NULL
        ALTER TABLE dbo.CrmConversation ADD IsPinned BIT NOT NULL
            CONSTRAINT DF_CrmConversation_IsPinned DEFAULT (0);
    """,
    """
    IF COL_LENGTH(N'dbo.CrmConversation', N'IsArchived') IS NULL
        ALTER TABLE dbo.CrmConversation ADD IsArchived BIT NOT NULL
            CONSTRAINT DF_CrmConversation_IsArchived DEFAULT (0);
    """,
    """
    IF COL_LENGTH(N'dbo.CrmConversation', N'IsStarred') IS NULL
        ALTER TABLE dbo.CrmConversation ADD IsStarred BIT NOT NULL
            CONSTRAINT DF_CrmConversation_IsStarred DEFAULT (0);
    """,
    """
    IF COL_LENGTH(N'dbo.CrmConversation', N'LastInboundAt') IS NULL
        ALTER TABLE dbo.CrmConversation ADD LastInboundAt DATETIME2 NULL;
    """,
    """
    IF COL_LENGTH(N'dbo.CrmConversation', N'LastOutboundAt') IS NULL
        ALTER TABLE dbo.CrmConversation ADD LastOutboundAt DATETIME2 NULL;
    """,
    """
    IF COL_LENGTH(N'dbo.CrmMessage', N'ExternalMessageID') IS NULL
        ALTER TABLE dbo.CrmMessage ADD ExternalMessageID NVARCHAR(128) NULL;
    """,
    """
    IF COL_LENGTH(N'dbo.CrmMessage', N'DeliveryStatus') IS NULL
        ALTER TABLE dbo.CrmMessage ADD DeliveryStatus NVARCHAR(30) NULL;
    """,
    """
    IF COL_LENGTH(N'dbo.CrmMessage', N'StatusUpdatedAt') IS NULL
        ALTER TABLE dbo.CrmMessage ADD StatusUpdatedAt DATETIME2 NULL;
    """,
    """
    IF COL_LENGTH(N'dbo.CrmMessage', N'AttachmentMimeType') IS NULL
        ALTER TABLE dbo.CrmMessage ADD AttachmentMimeType NVARCHAR(100) NULL;
    """,
    """
    IF COL_LENGTH(N'dbo.CrmMessage', N'AttachmentSizeBytes') IS NULL
        ALTER TABLE dbo.CrmMessage ADD AttachmentSizeBytes BIGINT NULL;
    """,
    """
    IF COL_LENGTH(N'dbo.CrmMessage', N'MediaType') IS NULL
        ALTER TABLE dbo.CrmMessage ADD MediaType NVARCHAR(30) NULL;
    """,
    """
    IF COL_LENGTH(N'dbo.CrmMessage', N'IsStarred') IS NULL
        ALTER TABLE dbo.CrmMessage ADD IsStarred BIT NOT NULL
            CONSTRAINT DF_CrmMessage_IsStarred DEFAULT (0);
    """,
    """
    IF COL_LENGTH(N'dbo.CrmMessage', N'ErrorDetail') IS NULL
        ALTER TABLE dbo.CrmMessage ADD ErrorDetail NVARCHAR(500) NULL;
    """,
    """
    IF OBJECT_ID(N'dbo.CrmQuickReply', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.CrmQuickReply (
            QuickReplyID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
            Title NVARCHAR(120) NOT NULL,
            Body NVARCHAR(MAX) NOT NULL,
            Channel NVARCHAR(50) NULL,
            Shortcut NVARCHAR(40) NULL,
            SortOrder INT NOT NULL CONSTRAINT DF_CrmQuickReply_Sort DEFAULT (0),
            IsActive BIT NOT NULL CONSTRAINT DF_CrmQuickReply_IsActive DEFAULT (1),
            CreatedByUserID INT NULL,
            CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_CrmQuickReply_Created DEFAULT (SYSUTCDATETIME()),
            ModifiedDate DATETIME2 NULL
        );
    END;
    """,
    """
    IF OBJECT_ID(N'dbo.CrmMessageTemplate', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.CrmMessageTemplate (
            TemplateID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
            Name NVARCHAR(150) NOT NULL,
            Channel NVARCHAR(50) NOT NULL CONSTRAINT DF_CrmMessageTemplate_Channel DEFAULT (N'WhatsApp'),
            Subject NVARCHAR(255) NULL,
            Body NVARCHAR(MAX) NOT NULL,
            ExternalTemplateName NVARCHAR(150) NULL,
            LanguageCode NVARCHAR(20) NULL,
            IsActive BIT NOT NULL CONSTRAINT DF_CrmMessageTemplate_IsActive DEFAULT (1),
            CreatedByUserID INT NULL,
            CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_CrmMessageTemplate_Created DEFAULT (SYSUTCDATETIME()),
            ModifiedDate DATETIME2 NULL
        );
    END;
    """,
    """
    IF OBJECT_ID(N'dbo.CrmCallLog', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.CrmCallLog (
            CallLogID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
            CustomerID INT NULL,
            LeadID INT NULL,
            ConversationID INT NULL,
            Direction NVARCHAR(20) NOT NULL CONSTRAINT DF_CrmCallLog_Direction DEFAULT (N'Outgoing'),
            CallStatus NVARCHAR(30) NOT NULL CONSTRAINT DF_CrmCallLog_Status DEFAULT (N'Completed'),
            PhoneNumber NVARCHAR(30) NULL,
            DurationSeconds INT NULL,
            RecordingURL NVARCHAR(500) NULL,
            Notes NVARCHAR(MAX) NULL,
            NextFollowUpAt DATETIME2 NULL,
            CalledAt DATETIME2 NOT NULL CONSTRAINT DF_CrmCallLog_CalledAt DEFAULT (SYSUTCDATETIME()),
            CreatedByUserID INT NULL,
            CreatedByName NVARCHAR(150) NULL,
            CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_CrmCallLog_Created DEFAULT (SYSUTCDATETIME()),
            IsActive BIT NOT NULL CONSTRAINT DF_CrmCallLog_IsActive DEFAULT (1)
        );
        CREATE INDEX IX_CrmCallLog_Customer ON dbo.CrmCallLog (CustomerID, CalledAt DESC);
    END;
    """,
)


def ensure_communication_center_schema() -> None:
    """ALTER/CREATE Communication Center columns and satellite tables (always safe)."""
    for stmt in _COMM_CENTER_ALTERS:
        db.session.execute(text(stmt))
        db.session.commit()


def ensure_crm_schema() -> None:
    """Create CRM tables if missing. Safe to call repeatedly."""
    global _SCHEMA_READY
    if not _SCHEMA_READY:
        for stmt in _STATEMENTS:
            db.session.execute(text(stmt))
            db.session.commit()
        _seed_default_workflow()
        _SCHEMA_READY = True
    ensure_communication_center_schema()


def ensure_crm_menus() -> None:
    """Activate CRM top-level menu and seed Communication Center menu tree."""
    row = db.session.execute(
        text(
            """
            SELECT TOP 1 MenuID FROM dbo.MenuMaster
            WHERE MenuName = N'CRM' AND ParentMenuID IS NULL
            """
        )
    ).first()
    if not row:
        db.session.execute(
            text(
                """
                INSERT INTO dbo.MenuMaster
                    (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
                VALUES
                    (NULL, N'CRM', N'bi-people', NULL, 25,
                     N'Customer Relationship Management', 1, NULL)
                """
            )
        )
        db.session.commit()
        row = db.session.execute(
            text(
                """
                SELECT TOP 1 MenuID FROM dbo.MenuMaster
                WHERE MenuName = N'CRM' AND ParentMenuID IS NULL
                """
            )
        ).first()
    if not row:
        return

    parent_id = int(row[0])
    db.session.execute(
        text(
            """
            UPDATE dbo.MenuMaster
            SET IsActive = 1,
                MenuIcon = N'bi-people',
                Description = N'Customer Relationship Management',
                DisplayOrder = 25,
                RoleName = NULL
            WHERE MenuID = :id
            """
        ),
        {"id": parent_id},
    )

    # Rename legacy "Follow-up" → "Follow-up Manager" when present
    db.session.execute(
        text(
            """
            UPDATE dbo.MenuMaster
            SET MenuName = N'Follow-up Manager',
                MenuURL = N'/crm/followups',
                IsActive = 1
            WHERE ParentMenuID = :parent AND MenuName = N'Follow-up'
            """
        ),
        {"parent": parent_id},
    )

    for name, icon, url, order, desc in _MENU_ITEMS:
        existing = db.session.execute(
            text(
                """
                SELECT TOP 1 MenuID FROM dbo.MenuMaster
                WHERE ParentMenuID = :parent AND MenuName = :name
                """
            ),
            {"parent": parent_id, "name": name},
        ).first()
        if existing:
            db.session.execute(
                text(
                    """
                    UPDATE dbo.MenuMaster
                    SET MenuIcon = :icon,
                        MenuURL = :url,
                        DisplayOrder = :ord,
                        Description = :desc,
                        IsActive = 1,
                        RoleName = NULL
                    WHERE MenuID = :id
                    """
                ),
                {
                    "icon": icon,
                    "url": url,
                    "ord": order,
                    "desc": desc,
                    "id": int(existing[0]),
                },
            )
        else:
            db.session.execute(
                text(
                    """
                    INSERT INTO dbo.MenuMaster
                        (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
                    VALUES
                        (:parent, :name, :icon, :url, :ord, :desc, 1, NULL)
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

    # Communication Center folder + channel children
    cc_row = db.session.execute(
        text(
            """
            SELECT TOP 1 MenuID FROM dbo.MenuMaster
            WHERE ParentMenuID = :parent AND MenuName = N'Communication Center'
            """
        ),
        {"parent": parent_id},
    ).first()
    if cc_row:
        cc_id = int(cc_row[0])
        # Folder node: no direct URL (children carry channel links)
        db.session.execute(
            text(
                """
                UPDATE dbo.MenuMaster
                SET MenuURL = NULL, MenuIcon = N'bi-chat-dots', IsActive = 1, DisplayOrder = 2
                WHERE MenuID = :id
                """
            ),
            {"id": cc_id},
        )
        for name, icon, url, order, desc in _COMM_CENTER_CHILDREN:
            child = db.session.execute(
                text(
                    """
                    SELECT TOP 1 MenuID FROM dbo.MenuMaster
                    WHERE ParentMenuID = :parent AND MenuName = :name
                    """
                ),
                {"parent": cc_id, "name": name},
            ).first()
            if child:
                db.session.execute(
                    text(
                        """
                        UPDATE dbo.MenuMaster
                        SET MenuIcon = :icon, MenuURL = :url, DisplayOrder = :ord,
                            Description = :desc, IsActive = 1, RoleName = NULL
                        WHERE MenuID = :id
                        """
                    ),
                    {
                        "icon": icon,
                        "url": url,
                        "ord": order,
                        "desc": desc,
                        "id": int(child[0]),
                    },
                )
            else:
                db.session.execute(
                    text(
                        """
                        INSERT INTO dbo.MenuMaster
                            (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
                        VALUES
                            (:parent, :name, :icon, :url, :ord, :desc, 1, NULL)
                        """
                    ),
                    {
                        "parent": cc_id,
                        "name": name,
                        "icon": icon,
                        "url": url,
                        "ord": order,
                        "desc": desc,
                    },
                )

    # Keep any other /crm/* rows active (legacy siblings)
    db.session.execute(
        text(
            """
            UPDATE dbo.MenuMaster
            SET IsActive = 1
            WHERE MenuURL LIKE N'/crm/%'
               OR MenuURL LIKE N'/crm/inbox%'
            """
        )
    )
    db.session.commit()


# Top-level menus that match the local ERP nav (everything else top-level is hidden).
ERP_CORE_TOP_LEVEL_MENUS = (
    "Admin Role",
    "Dashboard",
    "Activities",
    "Reports and Analysis",
    "Masters",
    "Accounting",
    "CRM",
)


def ensure_erp_core_nav_menus() -> None:
    """Keep legacy top modules hidden; allow Menu Customization additions.

    Only deactivates known legacy tops (ITR/GST/…) and old Settings/Menu Management.
    Does NOT wipe user-added main menus created via Menu Customization.
    DATA safe — only MenuMaster.IsActive changes for blocked names/URLs.
    """
    db.session.execute(
        text(
            """
            /* Explicit legacy top modules (belt-and-suspenders after VPS restore) */
            UPDATE dbo.MenuMaster
            SET IsActive = 0
            WHERE ParentMenuID IS NULL
              AND MenuName IN (
                    N'ITR', N'Others', N'GST', N'DSC', N'TDS',
                    N'Payroll', N'Transactions', N'Employee', N'Stock',
                    N'Menu Management', N'Settings'
              );

            /* Keep old Menu Management page hidden (new UI is Menu Customization) */
            UPDATE dbo.MenuMaster
            SET IsActive = 0,
                Description = N'Removed — use Admin Role → Menu Customization'
            WHERE MenuName IN (N'Settings', N'Menu Management', N'Menu Admin')
               OR LOWER(ISNULL(MenuURL, N'')) IN (N'/admin/menus', N'/admin/menus/', N'/settings', N'/settings/');

            /* Also deactivate children under removed top modules (stops them reappearing in nav) */
            UPDATE c
            SET c.IsActive = 0
            FROM dbo.MenuMaster AS c
            INNER JOIN dbo.MenuMaster AS p ON p.MenuID = c.ParentMenuID
            WHERE p.ParentMenuID IS NULL
              AND p.MenuName IN (
                    N'ITR', N'Others', N'GST', N'DSC', N'TDS',
                    N'Payroll', N'Transactions', N'Employee', N'Stock',
                    N'Menu Management', N'Settings'
              );

            /* Logout / orphan utility rows that should not be nav items */
            UPDATE dbo.MenuMaster
            SET IsActive = 0
            WHERE MenuName IN (N'Logout', N'Log Out')
               OR LOWER(ISNULL(MenuURL, N'')) IN (N'/logout', N'/auth/logout');

            """
        )
    )
    db.session.commit()
    # Separate batch so newly added BackgroundColor is visible to the parser.
    db.session.execute(
        text(
            """
            IF COL_LENGTH(N'dbo.MenuMaster', N'BackgroundColor') IS NULL
                ALTER TABLE dbo.MenuMaster ADD BackgroundColor NVARCHAR(20) NULL;
            """
        )
    )
    db.session.commit()
    db.session.execute(
        text(
            """
            UPDATE dbo.MenuMaster SET BackgroundColor = N'#257B24'
            WHERE ParentMenuID IS NULL AND MenuName = N'Dashboard';
            UPDATE dbo.MenuMaster SET BackgroundColor = N'#247B25'
            WHERE ParentMenuID IS NULL AND MenuName = N'Activities';
            UPDATE dbo.MenuMaster SET BackgroundColor = N'#247B29'
            WHERE ParentMenuID IS NULL AND MenuName = N'Reports and Analysis';
            UPDATE dbo.MenuMaster SET BackgroundColor = N'#247B3E'
            WHERE ParentMenuID IS NULL AND MenuName = N'Masters';
            """
        )
    )
    db.session.commit()


def ensure_activities_shcil_menus() -> None:
    """Keep Stamp + eCourt under Activities (never orphaned under hidden SHCIL)."""
    db.session.execute(
        text(
            """
            DECLARE @ActivitiesID INT = (
                SELECT TOP 1 MenuID FROM dbo.MenuMaster
                WHERE MenuName = N'Activities' AND ParentMenuID IS NULL
                ORDER BY MenuID
            );

            IF @ActivitiesID IS NULL
            BEGIN
                INSERT INTO dbo.MenuMaster
                    (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
                VALUES
                    (NULL, N'Activities', N'bi-lightning-charge', NULL, 2,
                     N'Daily operational activities', 1, NULL);
                SET @ActivitiesID = SCOPE_IDENTITY();
            END
            ELSE
                UPDATE dbo.MenuMaster SET IsActive = 1 WHERE MenuID = @ActivitiesID;

            IF NOT EXISTS (
                SELECT 1 FROM dbo.MenuMaster
                WHERE MenuURL = N'/shcil/stamp-activity' OR MenuName = N'Stamp Activity'
            )
                INSERT INTO dbo.MenuMaster
                    (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
                VALUES
                    (@ActivitiesID, N'Stamp Activity', N'bi-file-earmark-ruled',
                     N'/shcil/stamp-activity', 0, N'Uttarakhand e-Stamp manual entry and OCR', 1, NULL);
            ELSE
                UPDATE dbo.MenuMaster
                SET ParentMenuID = @ActivitiesID, MenuName = N'Stamp Activity',
                    MenuURL = N'/shcil/stamp-activity', MenuIcon = N'bi-file-earmark-ruled',
                    DisplayOrder = 0, IsActive = 1, RoleName = NULL
                WHERE MenuURL = N'/shcil/stamp-activity' OR MenuName = N'Stamp Activity';

            IF NOT EXISTS (
                SELECT 1 FROM dbo.MenuMaster
                WHERE MenuURL = N'/shcil/ecourt-activity'
                   OR MenuName IN (N'eCourt Activity', N'e-Court Activity', N'ecourt activity')
            )
                INSERT INTO dbo.MenuMaster
                    (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
                VALUES
                    (@ActivitiesID, N'eCourt Activity', N'bi-file-earmark-text',
                     N'/shcil/ecourt-activity', 1,
                     N'SHCIL e-Court fee receipt import and stationery sale check', 1, NULL);
            ELSE
                UPDATE dbo.MenuMaster
                SET ParentMenuID = @ActivitiesID, MenuName = N'eCourt Activity',
                    MenuURL = N'/shcil/ecourt-activity', MenuIcon = N'bi-file-earmark-text',
                    DisplayOrder = 1, IsActive = 1, RoleName = NULL
                WHERE MenuURL = N'/shcil/ecourt-activity'
                   OR MenuName IN (N'eCourt Activity', N'e-Court Activity', N'ecourt activity');

            UPDATE dbo.MenuMaster
            SET IsActive = 0
            WHERE MenuName = N'SHCIL' AND ParentMenuID IS NULL
              AND NOT EXISTS (
                    SELECT 1 FROM dbo.MenuMaster c
                    WHERE c.ParentMenuID = MenuMaster.MenuID AND c.IsActive = 1
              );
            """
        )
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
