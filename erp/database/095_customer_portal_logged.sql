-- Customer Portal: Logged flag on CustomerMaster (first password set / portal activated).
-- Idempotent: safe to re-run.

IF COL_LENGTH(N'dbo.CustomerMaster', N'Logged') IS NULL
BEGIN
    ALTER TABLE dbo.CustomerMaster ADD Logged BIT NOT NULL
        CONSTRAINT DF_CustomerMaster_Logged DEFAULT (0);
END
GO

/* Customers who already set a portal password count as logged/activated. */
UPDATE dbo.CustomerMaster
SET Logged = 1
WHERE ISNULL(PasswordChanged, 0) = 1
  AND ISNULL(Logged, 0) = 0;
GO
