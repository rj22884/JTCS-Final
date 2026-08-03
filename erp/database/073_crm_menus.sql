/*
    CRM MenuMaster seeds (idempotent).

    CRM is moving to a separate app — keep rows for reference / What's New
    history, but keep IsActive = 0 so they never appear in ERP navigation.
    (App startup also calls ensure_crm_menus() for the same policy.)
*/
USE JTCSS;
GO

DECLARE @CrmParentID INT = (
    SELECT TOP 1 MenuID FROM dbo.MenuMaster WHERE MenuName = N'CRM' AND ParentMenuID IS NULL
);

IF @CrmParentID IS NULL
BEGIN
    INSERT INTO dbo.MenuMaster (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
    VALUES (
        NULL,
        N'CRM',
        N'bi-people',
        NULL,
        25,
        N'Customer Relationship Management (moved to separate app)',
        0,
        NULL
    );
    SET @CrmParentID = SCOPE_IDENTITY();
END
ELSE
BEGIN
    UPDATE dbo.MenuMaster
    SET MenuIcon = N'bi-people',
        IsActive = 0,
        Description = N'Customer Relationship Management (moved to separate app)'
    WHERE MenuID = @CrmParentID;
END;

DECLARE @Items TABLE (
    MenuName NVARCHAR(100),
    MenuIcon NVARCHAR(100),
    MenuURL NVARCHAR(250),
    DisplayOrder INT,
    Description NVARCHAR(300)
);

INSERT INTO @Items (MenuName, MenuIcon, MenuURL, DisplayOrder, Description) VALUES
    (N'Dashboard', N'bi-speedometer2', N'/crm/dashboard', 1, N'CRM dashboard'),
    (N'Leads', N'bi-person-plus', N'/crm/leads', 2, N'CRM leads'),
    (N'Customer 360', N'bi-person-bounding-box', N'/crm/customer-360', 3, N'Customer 360 view'),
    (N'Communication Center', N'bi-chat-dots', N'/crm/inbox', 4, N'CRM inbox'),
    (N'Follow-up', N'bi-telephone-outbound', N'/crm/followups', 5, N'CRM follow-ups'),
    (N'Tasks', N'bi-check2-square', N'/crm/tasks', 6, N'CRM tasks'),
    (N'Timeline', N'bi-clock-history', N'/crm/timeline', 7, N'Activity timeline'),
    (N'Documents', N'bi-folder2-open', N'/crm/documents', 8, N'Document vault'),
    (N'Notifications', N'bi-bell', N'/crm/notifications', 9, N'Notifications'),
    (N'Workflow', N'bi-diagram-3', N'/crm/workflow', 10, N'CRM workflow'),
    (N'Calendar', N'bi-calendar-event', N'/crm/calendar', 11, N'CRM calendar'),
    (N'Analytics', N'bi-graph-up', N'/crm/analytics', 12, N'CRM reports'),
    (N'Audit Log', N'bi-shield-check', N'/crm/audit', 13, N'CRM audit log');

MERGE dbo.MenuMaster AS t
USING (
    SELECT @CrmParentID AS ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description
    FROM @Items
) AS s
ON t.ParentMenuID = s.ParentMenuID AND t.MenuName = s.MenuName
WHEN MATCHED THEN
    UPDATE SET
        MenuIcon = s.MenuIcon,
        MenuURL = s.MenuURL,
        DisplayOrder = s.DisplayOrder,
        Description = s.Description,
        IsActive = 0
WHEN NOT MATCHED THEN
    INSERT (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
    VALUES (s.ParentMenuID, s.MenuName, s.MenuIcon, s.MenuURL, s.DisplayOrder, s.Description, 0, NULL);

-- Any other /crm/* rows (safety)
UPDATE dbo.MenuMaster
SET IsActive = 0
WHERE MenuURL LIKE N'/crm/%'
   OR (MenuName = N'CRM' AND ParentMenuID IS NULL);

PRINT '073_crm_menus.sql completed (CRM menus kept inactive).';
GO
