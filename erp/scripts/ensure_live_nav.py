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
            N'Masters', N'Accounting', N'Others'
      );

    UPDATE dbo.MenuMaster
    SET IsActive = 0
    WHERE MenuName IN (N'Logout', N'Log Out')
       OR LOWER(ISNULL(MenuURL, N'')) IN (N'/logout', N'/auth/logout');
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
       OR MenuName IN (N'Exceptional Report', N'Stamp Exception', N'E-Court Exception', N'e-Court Exception')
       OR MenuURL LIKE N'/exceptional-report/%';
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

        forbidden = {
            "ITR",
            "GST",
            "DSC",
            "TDS",
            "Payroll",
            "Transactions",
            "Employee",
            "Stock",
            "Menu Management",
        }
        bad = forbidden.intersection(set(tops))
        if bad:
            print(f"[FAIL] Still active top menus that should be hidden: {sorted(bad)}")
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

        print("[PASS] Live nav menus ensured")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {exc}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
