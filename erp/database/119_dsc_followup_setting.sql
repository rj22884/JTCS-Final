/*
    DSC Followup — office-shared ID-Sign Business Id and customer video link.
*/
USE JTCSS;
GO

IF OBJECT_ID(N'dbo.DscFollowupSetting', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.DscFollowupSetting (
        SettingKey NVARCHAR(40) NOT NULL,
        SettingValue NVARCHAR(500) NULL,
        ModifiedBy NVARCHAR(150) NULL,
        ModifiedDate DATETIME NULL,
        CONSTRAINT PK_DscFollowupSetting PRIMARY KEY (SettingKey)
    );
END;
GO

PRINT '119_dsc_followup_setting.sql completed.';
GO
