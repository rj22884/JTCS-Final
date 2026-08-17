"""Smoke-test HR bootstrap, menus, application read, and auth gates."""
from __future__ import annotations

import sys
from pathlib import Path

ERP_ROOT = Path(r"E:\Git\JTCS Final\erp")
sys.path.insert(0, str(ERP_ROOT))

from app import create_app
from app.extensions import db
from app.models.menu_master import MenuMaster
from app.services import hr_service as hr
from app.services import recruitment_applications_service as rec
from sqlalchemy import text


def main() -> None:
    app = create_app()
    failures = 0
    with app.app_context():
        hr.bootstrap()
        tables = [
            "HrDepartment",
            "HrDesignation",
            "HrEmploymentType",
            "HrWorkLocation",
            "HrEmployee",
            "HrInterview",
            "HrOfferLetter",
            "HrAppointmentLetter",
            "HrLetterTemplate",
            "HrEmployeeDocument",
            "HrApplicationState",
        ]
        for table in tables:
            exists = db.session.execute(
                text(f"SELECT OBJECT_ID(N'dbo.{table}', N'U')")
            ).scalar()
            print(f"TABLE {table}: {'OK' if exists else 'MISSING'}")
            if not exists:
                failures += 1
        hr_menu = MenuMaster.query.filter(
            MenuMaster.MenuName == "HR",
            MenuMaster.ParentMenuID.is_(None),
        ).first()
        print("MENU HR:", "OK" if hr_menu and hr_menu.IsActive else "MISSING")
        if not hr_menu:
            failures += 1
        apps_menu = MenuMaster.query.filter(MenuMaster.MenuURL == "/hr/applications").first()
        print("MENU Applications:", "OK" if apps_menu else "MISSING")
        if not apps_menu:
            failures += 1
        dept_count = db.session.execute(text("SELECT COUNT(*) FROM dbo.HrDepartment")).scalar()
        print("DEPARTMENTS:", dept_count)
        available, message = rec.store_available()
        print("RECRUITMENT STORE:", available, message)
        if available:
            rows = rec.list_applications()
            print("EXISTING APPLICATIONS:", len(rows))
            for row in rows[:10]:
                print(" ", row.get("application_number"), row.get("name"), row.get("application_status"))
        kpis = hr.dashboard_kpis()
        print("KPI applications:", kpis["applications"], "employees:", kpis["employees"])
        from app.services.hr_letters import build_letter_pdf

        pdf = build_letter_pdf(
            title="OFFER LETTER",
            employee={
                "Name": "Test Candidate",
                "EmployeeCode": "EMP-2026-00001",
                "ApplicationNumber": "JTCS-SE-2026-00001",
                "designation_name": "Sales Executive",
                "department_name": "Sales",
                "JoiningDate": None,
                "location_name": "Haldwani",
                "SalaryCtc": 300000,
                "ProbationPeriod": "6 Months",
                "ReportingManager": "Manager",
                "employment_type_name": "Full Time",
            },
            letter_type="offer",
        )
        print("OFFER PDF bytes:", len(pdf), "OK" if pdf.startswith(b"%PDF") else "BAD")
        if not pdf.startswith(b"%PDF"):
            failures += 1

    client = app.test_client()
    anon = client.get("/hr/dashboard", follow_redirects=False)
    print("ANON /hr/dashboard:", anon.status_code)
    if anon.status_code not in {302, 401, 403}:
        print("FAIL: anonymous user reached HR")
        failures += 1
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["user_name"] = "HR Test"
        sess["role"] = "Operator"
    denied = client.get("/hr/dashboard", follow_redirects=False)
    print("OPERATOR /hr/dashboard:", denied.status_code)
    if denied.status_code not in {302, 401, 403}:
        print("FAIL: operator reached HR")
        failures += 1
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["user_name"] = "HR Test"
        sess["role"] = "Administrator"
    pages = [
        "/hr/dashboard",
        "/hr/applications",
        "/hr/pipeline",
        "/hr/interviews",
        "/hr/employees",
        "/hr/employees/directory",
        "/hr/letters/offers",
        "/hr/letters/templates",
        "/hr/masters/departments",
        "/hr/reports/recruitment",
        "/hr/actions",
        "/hr/jobs",
        "/hr/selected",
        "/hr/employees/documents",
        "/hr/employees/timeline",
        "/hr/employees/probation",
        "/hr/letters/appointments",
        "/hr/reports/employees",
        "/hr/reports/interviews",
        "/hr/reports/letters",
    ]
    for path in pages:
        resp = client.get(path)
        print(f"ADMIN {path}:", resp.status_code)
        if resp.status_code != 200:
            failures += 1
    print("RESULT:", "PASS" if failures == 0 else f"FAIL ({failures})")
    raise SystemExit(failures)


if __name__ == "__main__":
    main()
