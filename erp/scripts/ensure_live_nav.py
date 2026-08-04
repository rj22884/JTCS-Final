"""
Force-align MenuMaster for live ERP nav (no Flask/torch boot).

DATA safe. Run on VPS:
  .venv/bin/python scripts/ensure_live_nav.py
"""
from __future__ import annotations

import os
from pathlib import Path

import pyodbc
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def connect():
    server = os.getenv("DB_SERVER", r"JTCS\JTCS")
    database = os.getenv("DB_NAME", "JTCSS")
    driver = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
    trusted = os.getenv("DB_TRUSTED_CONNECTION", "1") == "1"
    user = os.getenv("DB_USER", "")
    password = os.getenv("DB_PASSWORD", "")
    trust = "TrustServerCertificate=yes;"
    if os.getenv("DB_TRUST_SERVER_CERTIFICATE", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        trust = ""
    if trusted:
        cs = (
            f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
            f"Trusted_Connection=yes;{trust}"
        )
    else:
        cs = (
            f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
            f"UID={user};PWD={password};{trust}"
        )
    return pyodbc.connect(cs, autocommit=True, timeout=30)


BATCHES = [
    """
    UPDATE dbo.MenuMaster
    SET IsActive = 0
    WHERE ParentMenuID IS NULL
      AND MenuName NOT IN (
            N'Admin Role', N'Dashboard', N'Activities', N'Reports and Analysis',
            N'Masters', N'Accounting'
      );

    UPDATE dbo.MenuMaster
    SET IsActive = 0
    WHERE ParentMenuID IS NULL
      AND MenuName IN (
            N'ITR', N'Others', N'GST', N'DSC', N'TDS',
            N'Payroll', N'Transactions', N'Employee', N'Stock',
            N'Menu Management', N'Settings', N'CRM'
      );

    /* Permanently remove customized Menu Management (Admin Role → Settings) */
    UPDATE dbo.MenuMaster
    SET IsActive = 0,
        Description = N'Removed — customized menu disabled'
    WHERE MenuName IN (N'Settings', N'Menu Management', N'Menu Admin')
       OR LOWER(ISNULL(MenuURL, N'')) IN (N'/admin/menus', N'/admin/menus/', N'/settings', N'/settings/');

    UPDATE dbo.MenuMaster
    SET IsActive = 0
    WHERE MenuName IN (N'Logout', N'Log Out')
       OR LOWER(ISNULL(MenuURL, N'')) IN (N'/logout', N'/auth/logout');
    """,
    """
    IF COL_LENGTH(N'dbo.MenuMaster', N'BackgroundColor') IS NULL
        ALTER TABLE dbo.MenuMaster ADD BackgroundColor NVARCHAR(20) NULL;
    """,
    """
    UPDATE dbo.MenuMaster SET BackgroundColor = N'#257B24'
    WHERE ParentMenuID IS NULL AND MenuName = N'Dashboard';
    UPDATE dbo.MenuMaster SET BackgroundColor = N'#247B25'
    WHERE ParentMenuID IS NULL AND MenuName = N'Activities';
    UPDATE dbo.MenuMaster SET BackgroundColor = N'#247B29'
    WHERE ParentMenuID IS NULL AND MenuName = N'Reports and Analysis';
    UPDATE dbo.MenuMaster SET BackgroundColor = N'#247B3E'
    WHERE ParentMenuID IS NULL AND MenuName = N'Masters';
    """,
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
        VALUES (NULL, N'Activities', N'bi-lightning-charge', NULL, 2, N'Daily operational activities', 1, NULL);
        SET @ActivitiesID = SCOPE_IDENTITY();
    END
    ELSE
        UPDATE dbo.MenuMaster SET IsActive = 1 WHERE MenuID = @ActivitiesID;

    IF NOT EXISTS (SELECT 1 FROM dbo.MenuMaster WHERE MenuURL = N'/shcil/stamp-activity' OR MenuName = N'Stamp Activity')
        INSERT INTO dbo.MenuMaster
            (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
        VALUES (@ActivitiesID, N'Stamp Activity', N'bi-file-earmark-ruled', N'/shcil/stamp-activity', 0,
                N'Uttarakhand e-Stamp manual entry and OCR', 1, NULL);
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
        VALUES (@ActivitiesID, N'eCourt Activity', N'bi-file-earmark-text', N'/shcil/ecourt-activity', 1,
                N'SHCIL e-Court fee receipt import and stationery sale check', 1, NULL);
    ELSE
        UPDATE dbo.MenuMaster
        SET ParentMenuID = @ActivitiesID, MenuName = N'eCourt Activity',
            MenuURL = N'/shcil/ecourt-activity', MenuIcon = N'bi-file-earmark-text',
            DisplayOrder = 1, IsActive = 1, RoleName = NULL
        WHERE MenuURL = N'/shcil/ecourt-activity'
           OR MenuName IN (N'eCourt Activity', N'e-Court Activity', N'ecourt activity');
    """,
    """
    UPDATE dbo.MenuMaster SET IsActive = 0
    WHERE MenuName = N'SHCIL' AND ParentMenuID IS NULL
      AND NOT EXISTS (
            SELECT 1 FROM dbo.MenuMaster c
            WHERE c.ParentMenuID = MenuMaster.MenuID AND c.IsActive = 1
      );

    UPDATE dbo.MenuMaster SET IsActive = 0
    WHERE (MenuName = N'CRM' AND ParentMenuID IS NULL)
       OR MenuURL LIKE N'/crm/%'
       OR (MenuName = N'Exceptional Report' AND ParentMenuID IS NULL);
    """,
    """
    DECLARE @ReportsID INT;
    DECLARE @LedgerOrder INT;
    DECLARE @StampOrder INT;
    DECLARE @EcourtOrder INT;

    SELECT TOP 1 @ReportsID = MenuID
    FROM dbo.MenuMaster
    WHERE ParentMenuID IS NULL
      AND (
            MenuURL = N'/Reports_and_analysis'
         OR MenuName IN (N'Reports and Analysis', N'Reports & Analysis', N'Reports_and_analysis')
      )
    ORDER BY MenuID;

    IF @ReportsID IS NULL
    BEGIN
        INSERT INTO dbo.MenuMaster
            (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
        VALUES (NULL, N'Reports and Analysis', N'bi-graph-up', NULL, 50, N'Reports and analysis', 1, NULL);
        SET @ReportsID = SCOPE_IDENTITY();
    END
    ELSE
        UPDATE dbo.MenuMaster SET IsActive = 1 WHERE MenuID = @ReportsID;

    IF NOT EXISTS (
        SELECT 1 FROM dbo.MenuMaster
        WHERE MenuURL = N'/Reports_and_analysis/ledger_report' OR MenuName = N'Ledger Report'
    )
        INSERT INTO dbo.MenuMaster
            (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
        VALUES (
            @ReportsID, N'Ledger Report', N'bi-journal-text',
            N'/Reports_and_analysis/ledger_report', 10,
            N'Search and preview bank, customer, work/category and item ledgers', 1, NULL
        );
    ELSE
        UPDATE dbo.MenuMaster
        SET ParentMenuID = @ReportsID, MenuName = N'Ledger Report',
            MenuURL = N'/Reports_and_analysis/ledger_report',
            MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-journal-text'),
            IsActive = 1
        WHERE MenuURL = N'/Reports_and_analysis/ledger_report' OR MenuName = N'Ledger Report';

    SELECT @LedgerOrder = MAX(DisplayOrder)
    FROM dbo.MenuMaster
    WHERE ParentMenuID = @ReportsID
      AND (MenuURL = N'/Reports_and_analysis/ledger_report' OR MenuName = N'Ledger Report');

    SET @StampOrder = ISNULL(@LedgerOrder, 10) + 10;
    SET @EcourtOrder = @StampOrder + 10;

    IF EXISTS (
        SELECT 1 FROM dbo.MenuMaster
        WHERE MenuURL = N'/exceptional-report/stamp-certificate'
           OR MenuName IN (N'Stamp Exception', N'Stamp Certificate Reconciliation')
    )
        UPDATE dbo.MenuMaster
        SET ParentMenuID = @ReportsID, MenuName = N'Stamp Exception',
            MenuURL = N'/exceptional-report/stamp-certificate',
            MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-file-earmark-spreadsheet'),
            DisplayOrder = @StampOrder, IsActive = 1, RoleName = NULL,
            Description = N'SHCIL stamp certificate reconciliation'
        WHERE MenuURL = N'/exceptional-report/stamp-certificate'
           OR MenuName IN (N'Stamp Exception', N'Stamp Certificate Reconciliation');
    ELSE
        INSERT INTO dbo.MenuMaster
            (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
        VALUES (
            @ReportsID, N'Stamp Exception', N'bi-file-earmark-spreadsheet',
            N'/exceptional-report/stamp-certificate', @StampOrder,
            N'SHCIL stamp certificate reconciliation', 1, NULL
        );

    IF EXISTS (
        SELECT 1 FROM dbo.MenuMaster
        WHERE MenuURL = N'/exceptional-report/ecourt-exception'
           OR MenuName IN (N'e-Court Exception', N'E-Court Exception')
    )
        UPDATE dbo.MenuMaster
        SET ParentMenuID = @ReportsID, MenuName = N'e-Court Exception',
            MenuURL = N'/exceptional-report/ecourt-exception',
            MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-journal-check'),
            DisplayOrder = @EcourtOrder, IsActive = 1, RoleName = NULL,
            Description = N'e-Court exceptional report'
        WHERE MenuURL = N'/exceptional-report/ecourt-exception'
           OR MenuName IN (N'e-Court Exception', N'E-Court Exception');
    ELSE
        INSERT INTO dbo.MenuMaster
            (ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName)
        VALUES (
            @ReportsID, N'e-Court Exception', N'bi-journal-check',
            N'/exceptional-report/ecourt-exception', @EcourtOrder,
            N'e-Court exceptional report', 1, NULL
        );

    UPDATE dbo.MenuMaster
    SET IsActive = 0
    WHERE MenuURL LIKE N'/exceptional-report/%'
      AND MenuURL NOT IN (
            N'/exceptional-report/stamp-certificate',
            N'/exceptional-report/ecourt-exception'
      );

    ;WITH d AS (
        SELECT MenuID,
               ROW_NUMBER() OVER (PARTITION BY MenuURL ORDER BY MenuID) AS rn
        FROM dbo.MenuMaster
        WHERE MenuURL IN (
            N'/exceptional-report/stamp-certificate',
            N'/exceptional-report/ecourt-exception'
        )
    )
    UPDATE m
    SET IsActive = 0
    FROM dbo.MenuMaster m
    INNER JOIN d ON d.MenuID = m.MenuID
    WHERE d.rn > 1;
    """,
]


def main() -> int:
    print("========================================")
    print("  JTCS ERP — Ensure live nav menus")
    print("========================================")
    print(f"  DB: {os.getenv('DB_SERVER')}\\{os.getenv('DB_NAME')}")
    try:
        conn = connect()
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] connect: {exc}")
        return 1
    try:
        cur = conn.cursor()
        for i, sql in enumerate(BATCHES, 1):
            cur.execute(sql)
            while cur.nextset():
                pass
            print(f"[OK] batch {i}/{len(BATCHES)}")

        print("--- TOP_ACTIVE ---")
        cur.execute(
            """
            SELECT MenuName FROM dbo.MenuMaster
            WHERE ParentMenuID IS NULL AND IsActive = 1
            ORDER BY DisplayOrder, MenuName
            """
        )
        tops = [r[0] for r in cur.fetchall()]
        for name in tops:
            print(f"  {name}")

        print("--- ACTIVITIES_CHILDREN ---")
        cur.execute(
            """
            SELECT m.MenuName, m.IsActive, m.MenuURL
            FROM dbo.MenuMaster m
            INNER JOIN dbo.MenuMaster p ON p.MenuID = m.ParentMenuID
            WHERE p.MenuName = N'Activities' AND p.ParentMenuID IS NULL
            ORDER BY m.DisplayOrder, m.MenuName
            """
        )
        for name, active, url in cur.fetchall():
            print(f"  {name} | active={int(bool(active))} | {url}")

        print("--- REPORTS_CHILDREN ---")
        cur.execute(
            """
            SELECT m.MenuName, m.IsActive, m.MenuURL, m.DisplayOrder
            FROM dbo.MenuMaster m
            INNER JOIN dbo.MenuMaster p ON p.MenuID = m.ParentMenuID
            WHERE p.MenuName IN (N'Reports and Analysis', N'Reports & Analysis')
              AND p.ParentMenuID IS NULL
              AND m.IsActive = 1
            ORDER BY m.DisplayOrder, m.MenuName
            """
        )
        reports_children = cur.fetchall()
        for name, active, url, order in reports_children:
            print(f"  {name} | active={int(bool(active))} | order={order} | {url}")

        forbidden = {
            "ITR",
            "Others",
            "GST",
            "DSC",
            "TDS",
            "Payroll",
            "Transactions",
            "Employee",
            "Stock",
            "Menu Management",
            "Settings",
        }
        bad = forbidden.intersection(set(tops))
        if bad:
            print(f"[FAIL] Still active top menus that should be hidden: {sorted(bad)}")
            return 1

        cur.execute(
            """
            SELECT COUNT(1) FROM dbo.MenuMaster
            WHERE IsActive = 1
              AND (
                    MenuName IN (N'Settings', N'Menu Management', N'Menu Admin')
                 OR LOWER(ISNULL(MenuURL, N'')) IN (N'/admin/menus', N'/admin/menus/')
              )
            """
        )
        if int(cur.fetchone()[0] or 0) > 0:
            print("[FAIL] Settings / Menu Management still active (customized menu)")
            return 1

        cur.execute(
            """
            SELECT COUNT(1) FROM dbo.MenuMaster m
            INNER JOIN dbo.MenuMaster p ON p.MenuID = m.ParentMenuID
            WHERE p.MenuName = N'Activities' AND p.ParentMenuID IS NULL
              AND m.IsActive = 1
              AND (m.MenuName = N'eCourt Activity' OR m.MenuURL = N'/shcil/ecourt-activity')
            """
        )
        if int(cur.fetchone()[0] or 0) < 1:
            print("[FAIL] eCourt Activity not active under Activities")
            return 1

        report_names = {r[0] for r in reports_children}
        if "Stamp Exception" not in report_names:
            print("[FAIL] Stamp Exception not active under Reports and Analysis")
            return 1
        if "e-Court Exception" not in report_names:
            print("[FAIL] e-Court Exception not active under Reports and Analysis")
            return 1

        print("[PASS] Live nav menus ensured")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {exc}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
