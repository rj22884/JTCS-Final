/*
    Masters menu — ensure Work/Category Master (WorkMaster) under Masters
*/
USE JTCSS;
GO

DECLARE @MastersID INT = (
    SELECT TOP 1 MenuID
    FROM dbo.MenuMaster
    WHERE MenuName = N'Masters' AND ParentMenuID IS NULL
    ORDER BY MenuID
);

IF @MastersID IS NULL
BEGIN
    PRINT '046_masters_work_category_menu.sql skipped: Masters parent menu not found.';
END
ELSE
BEGIN
    /* Rename legacy Income/Expense menu rows to Work/Category Master */
    UPDATE dbo.MenuMaster
    SET MenuName = N'Work/Category Master',
        MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-sliders'),
        MenuURL = N'/masters/income-expense',
        DisplayOrder = 2,
        Description = N'Work / category master (Income, Expense, Misc.)',
        IsActive = 1,
        RoleName = NULL
    WHERE ParentMenuID = @MastersID
      AND (
          MenuName IN (N'Income/Expense', N'Income Expense', N'Work Master')
          OR MenuURL = N'/masters/income-expense'
      )
      AND MenuName <> N'Work/Category Master';

    IF EXISTS (
        SELECT 1
        FROM dbo.MenuMaster
        WHERE ParentMenuID = @MastersID
          AND MenuName = N'Work/Category Master'
    )
    BEGIN
        UPDATE dbo.MenuMaster
        SET MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-sliders'),
            MenuURL = N'/masters/income-expense',
            DisplayOrder = 2,
            Description = N'Work / category master (Income, Expense, Misc.)',
            IsActive = 1,
            RoleName = NULL
        WHERE ParentMenuID = @MastersID
          AND MenuName = N'Work/Category Master';
    END
    ELSE
    BEGIN
        INSERT INTO dbo.MenuMaster (
            ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
            Description, IsActive, RoleName
        )
        VALUES (
            @MastersID,
            N'Work/Category Master',
            N'bi-sliders',
            N'/masters/income-expense',
            2,
            N'Work / category master (Income, Expense, Misc.)',
            1,
            NULL
        );
    END
END;
GO

PRINT '046_masters_work_category_menu.sql completed.';
GO
