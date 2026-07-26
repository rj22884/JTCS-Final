/*
    JTCS ERP - Seed module menus (idempotent)
    Run after 001_create_menu_master.sql

    Adds Transactions hub, business modules (GST, DSC, SHCIL, TDS, Accounting,
    Payroll, Employee, Stock), report shortcuts, and admin links.
    Safe to re-run: inserts only when ParentMenuID + MenuName is missing.
*/

SET NOCOUNT ON;
GO

/* ---- helper: insert menu if not exists ---- */
IF OBJECT_ID('tempdb..#MenuSeed') IS NOT NULL DROP TABLE #MenuSeed;
CREATE TABLE #MenuSeed (
    ParentName      NVARCHAR(100) NULL,
    MenuName        NVARCHAR(100) NOT NULL,
    MenuIcon        NVARCHAR(100) NULL,
    MenuURL         NVARCHAR(250) NULL,
    DisplayOrder    INT NOT NULL,
    Description     NVARCHAR(300) NULL,
    RoleName        NVARCHAR(50) NULL
);
GO

INSERT INTO #MenuSeed (ParentName, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, RoleName)
VALUES
    /* Transactions hub */
    (NULL,           N'Transactions',       N'bi-cash-stack',       NULL,                                              15, N'Daily transactions and contra transfers', NULL),
    (N'Transactions', N'Daily Transaction', N'bi-plus-circle',      N'/transactions/new',                              1,  N'New daily business transaction', NULL),
    (N'Transactions', N'Contra Entry',      N'bi-arrow-left-right', N'/transactions/contra',                           2,  N'Cash / bank contra transfer', NULL),

    /* Reports shortcuts (parent Reports already seeded in 001) */
    (N'Reports',     N'Daily Collection',   N'bi-calendar-day',     N'/reports/daily-collection',                      1,  N'Daily collection summary', NULL),
    (N'Reports',     N'Cash Book',          N'bi-cash',             N'/reports/cash-book',                             2,  N'Cash book from bank transactions', NULL),
    (N'Reports',     N'Bank Book',          N'bi-bank',             N'/reports/bank-book',                             3,  N'Bank book from bank transactions', NULL),
    (N'Reports',     N'Income Report',      N'bi-graph-up-arrow',   N'/reports/income',                                4,  N'Income by work type', NULL),
    (N'Reports',     N'Expense Report',     N'bi-graph-down-arrow', N'/reports/expense',                               5,  N'Expense by work type', NULL),
    (N'Reports',     N'Work Wise Report',   N'bi-diagram-3',        N'/reports/work-wise',                             6,  N'Work-wise totals', NULL),
    (N'Reports',     N'Customer Ledger',    N'bi-person-lines-fill',N'/reports/customer-ledger',                     7,  N'Customer-wise ledger', NULL),
    (N'Reports',     N'Payment Mode',       N'bi-wallet2',          N'/reports/payment-mode',                          8,  N'Payment mode summary', NULL),
    (N'Reports',     N'Cash Flow',          N'bi-currency-exchange',N'/reports/cash-flow',                             9,  N'Cash flow summary', NULL),
    (N'Reports',     N'Bank Balance',       N'bi-piggy-bank',       N'/reports/bank-balance',                         10,  N'Bank balance snapshot', NULL),
    (N'Reports',     N'Outstanding',        N'bi-exclamation-circle',N'/reports/outstanding',                          11,  N'Outstanding balances', NULL),

    /* GST */
    (NULL,           N'GST',                N'bi-receipt',          NULL,                                              20, N'GST filing and compliance', NULL),
    (N'GST',         N'New GST Entry',      N'bi-plus-lg',          N'/transactions/new?work_type=GST',                1,  N'Record GST-related transaction', NULL),
    (N'GST',         N'GSTR-1 Filing',      N'bi-file-earmark-text',N'/transactions/new?work_type=GST&sub_work_type=GSTR-1', 2, N'GSTR-1 return filing fee', NULL),
    (N'GST',         N'GSTR-3B Filing',     N'bi-file-earmark-check',N'/transactions/new?work_type=GST&sub_work_type=GSTR-3B', 3, N'GSTR-3B return filing fee', NULL),
    (N'GST',         N'GST Register',       N'bi-journal-text',     N'/gst/register',                                  4,  N'GST register (coming soon)', NULL),

    /* DSC */
    (NULL,           N'DSC',                N'bi-shield-check',     NULL,                                              21, N'Digital Signature Certificate', NULL),
    (N'DSC',         N'New DSC Application',N'bi-plus-lg',          N'/transactions/new?work_type=DSC&sub_work_type=New Application', 1, N'New DSC application fee', NULL),
    (N'DSC',         N'DSC Renewal',        N'bi-arrow-repeat',     N'/transactions/new?work_type=DSC&sub_work_type=Renewal', 2, N'DSC renewal fee', NULL),
    (N'DSC',         N'DSC Status',         N'bi-search',           N'/dsc/status',                                    3,  N'DSC status tracker (coming soon)', NULL),

    /* SHCIL */
    (NULL,           N'SHCIL',              N'bi-bank2',            NULL,                                              22, N'SHCIL / e-stamping', NULL),
    (N'SHCIL',       N'Stamp Activity',     N'bi-file-earmark-ruled', N'/shcil/stamp-activity',                        1, N'SHCIL stamp activity (manual / OCR)', NULL),

    /* TDS */
    (NULL,           N'TDS',                N'bi-percent',          NULL,                                              23, N'Tax Deducted at Source', NULL),
    (N'TDS',         N'TDS Payment',        N'bi-cash-coin',        N'/transactions/new?work_type=TDS&sub_work_type=Payment', 1, N'TDS payment entry', NULL),
    (N'TDS',         N'TDS Return Filing',  N'bi-file-earmark-arrow-up',N'/transactions/new?work_type=TDS&sub_work_type=Return Filing', 2, N'TDS return filing fee', NULL),
    (N'TDS',         N'TDS Register',       N'bi-journal-text',     N'/tds/register',                                  3,  N'TDS register (coming soon)', NULL),

    /* Accounting */
    (NULL,           N'Accounting',         N'bi-journal-bookmark', NULL,                                              24, N'Accounting and ledgers', NULL),
    (N'Accounting',  N'Journal Entry',      N'bi-pencil-square',    N'/transactions/new?work_type=Accounting&sub_work_type=Journal', 1, N'General journal entry', NULL),
    (N'Accounting',  N'Ledger View',        N'bi-book',             N'/accounting/ledger',                             2,  N'Ledger view (coming soon)', NULL),
    (N'Accounting',  N'Trial Balance',      N'bi-calculator',       N'/accounting/trial-balance',                      3,  N'Trial balance (coming soon)', NULL),

    /* Payroll */
    (NULL,           N'Payroll',            N'bi-people',           NULL,                                              25, N'Payroll and salary', NULL),
    (N'Payroll',     N'Salary Payment',     N'bi-cash-stack',       N'/transactions/new?work_type=Payroll&sub_work_type=Salary Payment', 1, N'Monthly salary payment', NULL),
    (N'Payroll',     N'PF / ESI',           N'bi-building',         N'/transactions/new?work_type=Payroll&sub_work_type=PF ESI', 2, N'PF and ESI remittance', NULL),
    (N'Payroll',     N'Payroll Register',   N'bi-journal-text',     N'/payroll/register',                              3,  N'Payroll register (coming soon)', NULL),

    /* Employee */
    (NULL,           N'Employee',           N'bi-person-badge',     NULL,                                              26, N'Employee management', NULL),
    (N'Employee',    N'Employee List',      N'bi-people-fill',      N'/employee/list',                                 1,  N'Employee master list (coming soon)', NULL),
    (N'Employee',    N'Attendance',         N'bi-calendar-check',   N'/employee/attendance',                           2,  N'Attendance tracking (coming soon)', NULL),
    (N'Employee',    N'Leave Management',   N'bi-calendar-x',       N'/employee/leave',                                3,  N'Leave requests (coming soon)', NULL),

    /* Stock */
    (NULL,           N'Stock',              N'bi-box-seam',         NULL,                                              27, N'Inventory and stock', NULL),
    (N'Stock',       N'Stock Purchase',     N'bi-bag-plus',         N'/transactions/new?work_type=Stock&sub_work_type=Purchase', 1, N'Purchase stock items', NULL),
    (N'Stock',       N'Stock Sale',         N'bi-bag-check',        N'/transactions/new?work_type=Stock&sub_work_type=Sale', 2, N'Sell stock items', NULL),
    (N'Stock',       N'Stock Register',     N'bi-journal-text',     N'/stock/register',                                3,  N'Stock register (coming soon)', NULL),

    /* Exceptional Report */
    (NULL,           N'Exceptional Report', N'bi-clipboard-data',   NULL,                                              28, N'Exceptional and special reports', NULL),
    (N'Exceptional Report', N'Stamp Exception', N'bi-file-earmark-spreadsheet', N'/exceptional-report/stamp-certificate', 1, N'SHCIL stamp certificate reconciliation', NULL),
    (N'Exceptional Report', N'e-Court Exception', N'bi-journal-check', N'/exceptional-report/ecourt-exception', 2, N'e-Court exceptional report (coming soon)', NULL),

    /* ITR transaction shortcuts (ITR parent exists from 001) */
    (N'ITR',         N'ITR Filing Fee',     N'bi-currency-rupee',   N'/transactions/new?work_type=ITR&sub_work_type=ITR Filing', 5, N'Record ITR filing fee', NULL),

    /* Administration shortcuts */
    (N'Administration', N'Menu Management', N'bi-menu-button-wide', N'/admin/menus',                                   1,  N'Dynamic sidebar menu CRUD', N'Administrator');
GO

/* Update Data Entry to point at transaction form (idempotent) */
UPDATE dbo.MenuMaster
SET MenuURL = N'/transactions/new',
    Description = N'Daily data entry — opens transaction form'
WHERE MenuName = N'Data Entry'
  AND ParentMenuID IS NULL
  AND (MenuURL IS NULL OR MenuURL = N'/data-entry');
GO

DECLARE @ParentID INT;
DECLARE @ParentName NVARCHAR(100);
DECLARE @MenuName NVARCHAR(100);
DECLARE @MenuIcon NVARCHAR(100);
DECLARE @MenuURL NVARCHAR(250);
DECLARE @DisplayOrder INT;
DECLARE @Description NVARCHAR(300);
DECLARE @RoleName NVARCHAR(50);

DECLARE seed_cursor CURSOR LOCAL FAST_FORWARD FOR
    SELECT ParentName, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, RoleName
    FROM #MenuSeed
    ORDER BY CASE WHEN ParentName IS NULL THEN 0 ELSE 1 END, DisplayOrder, MenuName;

OPEN seed_cursor;
FETCH NEXT FROM seed_cursor INTO @ParentName, @MenuName, @MenuIcon, @MenuURL, @DisplayOrder, @Description, @RoleName;

WHILE @@FETCH_STATUS = 0
BEGIN
    SET @ParentID = NULL;
    IF @ParentName IS NOT NULL
    BEGIN
        SELECT @ParentID = MenuID
        FROM dbo.MenuMaster
        WHERE MenuName = @ParentName
          AND (
              (@ParentName IN (N'Reports', N'Administration', N'ITR') AND ParentMenuID IS NULL)
              OR ParentMenuID IS NOT NULL
          );

        IF @ParentID IS NULL
        BEGIN
            SELECT TOP 1 @ParentID = MenuID
            FROM dbo.MenuMaster
            WHERE MenuName = @ParentName
            ORDER BY MenuID;
        END
    END

    IF NOT EXISTS (
        SELECT 1
        FROM dbo.MenuMaster
        WHERE MenuName = @MenuName
          AND (
              (ParentMenuID IS NULL AND @ParentID IS NULL)
              OR ParentMenuID = @ParentID
          )
    )
    BEGIN
        INSERT INTO dbo.MenuMaster
            (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, IsActive, Description, RoleName)
        VALUES
            (@ParentID, @MenuName, @MenuIcon, @MenuURL, @DisplayOrder, 1, @Description, @RoleName);
    END

    FETCH NEXT FROM seed_cursor INTO @ParentName, @MenuName, @MenuIcon, @MenuURL, @DisplayOrder, @Description, @RoleName;
END

CLOSE seed_cursor;
DEALLOCATE seed_cursor;
GO

DROP TABLE #MenuSeed;
GO

PRINT '003_seed_module_menus.sql completed.';
GO
