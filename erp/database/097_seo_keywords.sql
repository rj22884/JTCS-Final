/*
    JTCS ERP — SEO Keyword Management
    Table + preload keywords + Admin Role menu (idempotent)
*/
SET NOCOUNT ON;
GO

IF OBJECT_ID(N'dbo.seo_keywords', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.seo_keywords (
        id INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_seo_keywords PRIMARY KEY,
        keyword NVARCHAR(255) NOT NULL,
        is_active BIT NOT NULL
            CONSTRAINT DF_seo_keywords_is_active DEFAULT (1),
        created_at DATETIME2 NOT NULL
            CONSTRAINT DF_seo_keywords_created_at DEFAULT (SYSUTCDATETIME())
    );
    CREATE UNIQUE INDEX UX_seo_keywords_keyword ON dbo.seo_keywords (keyword);
    CREATE INDEX IX_seo_keywords_active ON dbo.seo_keywords (is_active, id);
END;
GO

;WITH seed (keyword) AS (
    SELECT v.keyword
    FROM (VALUES
        (N'income tax consultant'),
        (N'GST services'),
        (N'TDS return filing'),
        (N'ITR filing India'),
        (N'web app developer'),
        (N'ERP software'),
        (N'stamp vendor near me'),
        (N'CSC services'),
        (N'government forms'),
        (N'banking services'),
        (N'digital signature DSC'),
        (N'certificate services'),
        (N'annexure forms'),
        (N'online application'),
        (N'accounting services Haldwani'),
        (N'Uttarakhand'),
        (N'India'),
        (N'Uttar Pradesh'),
        (N'Almora'),
        (N'Kumaon'),
        (N'Garhwal'),
        (N'Nainital'),
        (N'Pithoragarh'),
        (N'Ramnagar'),
        (N'Rudrapur'),
        (N'Udham Singh Nagar'),
        (N'Sitarganj'),
        (N'Khatima'),
        (N'Banbasa'),
        (N'Pilibhit'),
        (N'Rampur'),
        (N'Moradabad'),
        (N'Delhi'),
        (N'New Delhi'),
        (N'Ranikhet'),
        (N'Dwarahat'),
        (N'Karnaprayag'),
        (N'Haridwar'),
        (N'Dehradun'),
        (N'Rishikesh'),
        (N'Himachal'),
        (N'Mandi'),
        (N'Punjab'),
        (N'Kharar')
    ) AS v(keyword)
)
INSERT INTO dbo.seo_keywords (keyword, is_active)
SELECT s.keyword, 1
FROM seed s
WHERE NOT EXISTS (
    SELECT 1
    FROM dbo.seo_keywords k
    WHERE LOWER(LTRIM(RTRIM(k.keyword))) = LOWER(LTRIM(RTRIM(s.keyword)))
);
GO

DECLARE @ParentID INT;
DECLARE @AdminRoles NVARCHAR(50) = N'Administrator,Admin';

SELECT TOP 1 @ParentID = MenuID
FROM dbo.MenuMaster
WHERE MenuName = N'Admin Role'
  AND ParentMenuID IS NULL
ORDER BY MenuID;

IF @ParentID IS NULL
BEGIN
    INSERT INTO dbo.MenuMaster (
        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
        Description, IsActive, RoleName
    )
    VALUES (
        NULL, N'Admin Role', N'bi-archive', NULL, 1,
        N'Administrator tools', 1, @AdminRoles
    );
    SET @ParentID = SCOPE_IDENTITY();
END;

IF EXISTS (
    SELECT 1 FROM dbo.MenuMaster
    WHERE ParentMenuID = @ParentID AND MenuName = N'SEO Keywords'
)
BEGIN
    UPDATE dbo.MenuMaster
    SET MenuURL = N'/admin/seo',
        MenuIcon = N'bi-search',
        DisplayOrder = 65,
        Description = N'Manage SEO keywords for meta, footer, and schema',
        IsActive = 1,
        RoleName = @AdminRoles
    WHERE ParentMenuID = @ParentID AND MenuName = N'SEO Keywords';
END
ELSE IF EXISTS (
    SELECT 1 FROM dbo.MenuMaster WHERE MenuURL = N'/admin/seo'
)
BEGIN
    UPDATE dbo.MenuMaster
    SET ParentMenuID = @ParentID,
        MenuName = N'SEO Keywords',
        MenuIcon = N'bi-search',
        DisplayOrder = 65,
        Description = N'Manage SEO keywords for meta, footer, and schema',
        IsActive = 1,
        RoleName = @AdminRoles
    WHERE MenuURL = N'/admin/seo';
END
ELSE
BEGIN
    INSERT INTO dbo.MenuMaster (
        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
        Description, IsActive, RoleName
    )
    VALUES (
        @ParentID, N'SEO Keywords', N'bi-search', N'/admin/seo', 65,
        N'Manage SEO keywords for meta, footer, and schema', 1, @AdminRoles
    );
END;
GO

PRINT '097_seo_keywords.sql completed.';
GO
