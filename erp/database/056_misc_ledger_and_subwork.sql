/*
    Misc. ledger kind + WorkTypeMaster parent/child (WorkTypeName / SubWorkType)
    + seed NSDL / New-Pan + Sub Work Master menu
*/
USE JTCSS;
GO

/* 1) WorkMaster: allow Misc. */
IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = N'CK_WorkMaster_LedgerKind'
      AND parent_object_id = OBJECT_ID(N'dbo.WorkMaster')
)
BEGIN
    ALTER TABLE dbo.WorkMaster DROP CONSTRAINT CK_WorkMaster_LedgerKind;
END;
GO

ALTER TABLE dbo.WorkMaster WITH NOCHECK
ADD CONSTRAINT CK_WorkMaster_LedgerKind
CHECK (LedgerKind IN (N'Income', N'Expense', N'Misc.'));
GO

IF NOT EXISTS (
    SELECT 1 FROM dbo.WorkMaster
    WHERE WorkName = N'NSDL' AND LedgerKind = N'Misc.'
)
BEGIN
    INSERT INTO dbo.WorkMaster (WorkName, LedgerKind, ActiveStatus)
    VALUES (N'NSDL', N'Misc.', 1);
END;
GO

/* 2) WorkTypeMaster: add parent WorkTypeName, rename old name -> SubWorkType */
IF COL_LENGTH(N'dbo.WorkTypeMaster', N'SubWorkType') IS NULL
   AND COL_LENGTH(N'dbo.WorkTypeMaster', N'WorkTypeName') IS NOT NULL
BEGIN
    ALTER TABLE dbo.WorkTypeMaster ADD WorkTypeNameNew NVARCHAR(100) NULL;

    EXEC sp_executesql N'
        UPDATE dbo.WorkTypeMaster
        SET WorkTypeNameNew = WorkTypeName
        WHERE WorkTypeNameNew IS NULL;
    ';

    EXEC sp_rename N'dbo.WorkTypeMaster.WorkTypeName', N'SubWorkType', N'COLUMN';
    EXEC sp_rename N'dbo.WorkTypeMaster.WorkTypeNameNew', N'WorkTypeName', N'COLUMN';

    ALTER TABLE dbo.WorkTypeMaster ALTER COLUMN WorkTypeName NVARCHAR(100) NOT NULL;
    ALTER TABLE dbo.WorkTypeMaster ALTER COLUMN SubWorkType NVARCHAR(100) NOT NULL;
END;
GO

/* Unique parent + sub-work */
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UX_WorkTypeMaster_Name_Sub'
      AND object_id = OBJECT_ID(N'dbo.WorkTypeMaster')
)
BEGIN
    CREATE UNIQUE INDEX UX_WorkTypeMaster_Name_Sub
        ON dbo.WorkTypeMaster (WorkTypeName, SubWorkType);
END;
GO

IF COL_LENGTH(N'dbo.WorkTypeMaster', N'SubWorkType') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM dbo.WorkTypeMaster
        WHERE WorkTypeName = N'NSDL' AND SubWorkType = N'New-Pan'
   )
BEGIN
    EXEC sp_executesql N'
        INSERT INTO dbo.WorkTypeMaster (WorkTypeName, SubWorkType, ActiveStatus)
        VALUES (N''NSDL'', N''New-Pan'', 1);
    ';
END;
GO

IF COL_LENGTH(N'dbo.WorkTypeMaster', N'SubWorkType') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM dbo.WorkTypeMaster
        WHERE WorkTypeName = N'New Pan application' AND SubWorkType = N'New-Pan'
   )
BEGIN
    EXEC sp_executesql N'
        INSERT INTO dbo.WorkTypeMaster (WorkTypeName, SubWorkType, ActiveStatus)
        VALUES (N''New Pan application'', N''New-Pan'', 1);
    ';
END;
GO

/* 3) Detail lines: optional Sub Work (WorkTypeID) */
IF COL_LENGTH(N'dbo.OthersIncomeExpenseDetail', N'WorkTypeID') IS NULL
BEGIN
    ALTER TABLE dbo.OthersIncomeExpenseDetail ADD WorkTypeID INT NULL;

    ALTER TABLE dbo.OthersIncomeExpenseDetail WITH NOCHECK
    ADD CONSTRAINT FK_OthersIncomeExpenseDetail_WorkType
        FOREIGN KEY (WorkTypeID) REFERENCES dbo.WorkTypeMaster (WorkTypeID);
END;
GO

/* 4) Masters → Sub Work Master menu */
DECLARE @MastersID INT;
SELECT TOP 1 @MastersID = MenuID
FROM dbo.MenuMaster
WHERE MenuName = N'Masters' AND ParentMenuID IS NULL
ORDER BY MenuID;

IF @MastersID IS NOT NULL
BEGIN
    IF EXISTS (
        SELECT 1 FROM dbo.MenuMaster
        WHERE ParentMenuID = @MastersID AND MenuName = N'Sub Work Master'
    )
    BEGIN
        UPDATE dbo.MenuMaster
        SET MenuURL = N'/masters/sub-work',
            MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-diagram-3'),
            DisplayOrder = 3,
            Description = N'Sub work types for Misc. Income/Expense (WorkTypeName → SubWorkType)',
            IsActive = 1,
            RoleName = NULL
        WHERE ParentMenuID = @MastersID AND MenuName = N'Sub Work Master';
    END
    ELSE
    BEGIN
        INSERT INTO dbo.MenuMaster (
            ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
            Description, IsActive, RoleName
        )
        VALUES (
            @MastersID,
            N'Sub Work Master',
            N'bi-diagram-3',
            N'/masters/sub-work',
            3,
            N'Sub work types for Misc. Income/Expense (WorkTypeName → SubWorkType)',
            1,
            NULL
        );
    END
END;
GO

PRINT '056_misc_ledger_and_subwork.sql completed.';
GO
