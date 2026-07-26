-- Customer Master: GST Filing Frequency (Monthly / Quarterly / Yearly)
IF COL_LENGTH(N'dbo.CustomerMaster', N'FilingFrequency') IS NULL
    ALTER TABLE dbo.CustomerMaster ADD FilingFrequency NVARCHAR(20) NULL;
GO
