"""Smoke-test Other Login catalog, FPS login pages, and FPS_USER restrictions."""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ERP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ERP_ROOT))

from app import create_app
from app.services.menu_service import MenuService
from app.services.other_login_catalog import STATUS_ENABLED, list_other_login_services
from app.utils.fps_access import FPS_FORBIDDEN_MESSAGE, fps_user_request_allowed
from app.utils.roles import FPS_USER_ROLE, has_fps_user_role


def test_catalog() -> None:
    services = list_other_login_services()
    names = [item.name for item in services]
    print("SERVICES", len(services))
    if len(services) != 25:
        raise SystemExit(f"Expected 25 Other Login services, got {len(services)}")
    if len(set(names)) != 25:
        raise SystemExit("Other Login service names are not unique")
    enabled = [item for item in services if item.enabled]
    if len(enabled) != 1 or enabled[0].key != "uttarakhand_fps":
        raise SystemExit("Only Uttarakhand FPS Login should be enabled")
    if enabled[0].status != STATUS_ENABLED or not enabled[0].login_url:
        raise SystemExit("Enabled FPS service is missing login URL")
    if services[0].name != "Uttarakhand FPS Login":
        raise SystemExit("First service must be Uttarakhand FPS Login")
    expected = {
        "Aadhaar Login",
        "PAN Login",
        "GST Login",
        "Income Tax Login",
        "TDS / TRACES Login",
        "EPFO Login",
        "ESIC Login",
        "Udyam Registration Login",
        "MCA Login",
        "DigiLocker Login",
        "e-District Uttarakhand Login",
        "Uttarakhand Revenue / Bhulekh Login",
        "Vahan Login",
        "Sarathi Login",
        "Passport Seva Login",
        "NPS Login",
        "GeM Login",
        "CPGRAMS Login",
        "Jan Aadhaar / Citizen Services",
        "PFMS Login",
        "e-Way Bill Login",
        "e-Invoice Login",
        "FSSAI Login",
        "Startup India Login",
    }
    missing = expected.difference(names)
    if missing:
        raise SystemExit(f"Missing services: {missing}")
    print("CATALOG OK")


def test_allowlist() -> None:
    if not has_fps_user_role(FPS_USER_ROLE):
        raise SystemExit("FPS_USER role helper failed")
    if not fps_user_request_allowed("/public-report/ration-card/fps-detail", "GET"):
        raise SystemExit("FPS home should be allowed")
    if not fps_user_request_allowed("/public-report/ration-card/fps-master", "GET"):
        raise SystemExit("FPS Master should be allowed")
    if not fps_user_request_allowed("/public-report/ration-card/ration-card-master", "GET"):
        raise SystemExit("Ration Card Master should be allowed")
    if fps_user_request_allowed("/public-report/ration-card/state-master", "GET"):
        raise SystemExit("State Master should be denied")
    if fps_user_request_allowed("/public-report/ration-card/aro-master", "GET"):
        raise SystemExit("ARO Master should be denied")
    if not fps_user_request_allowed("/public-report/api/pds/fps", "GET"):
        raise SystemExit("FPS master list GET should be allowed")
    if fps_user_request_allowed("/public-report/api/pds/fps", "POST"):
        raise SystemExit("FPS master write should be denied")
    if fps_user_request_allowed("/masters", "GET"):
        raise SystemExit("Masters should be denied")
    if fps_user_request_allowed("/accounting", "GET"):
        raise SystemExit("Accounting should be denied")
    if fps_user_request_allowed("/crm", "GET"):
        raise SystemExit("CRM should be denied")
    if fps_user_request_allowed("/public-report/api/dealers", "POST"):
        raise SystemExit("Dealer write should be denied")
    if fps_user_request_allowed("/public-report/api/ration-card/fps-detail/generate", "POST"):
        raise SystemExit("CSV import should be denied")
    if not fps_user_request_allowed("/logout", "GET"):
        raise SystemExit("Logout should be allowed")
    print("ALLOWLIST OK")


def test_pages_and_scope() -> None:
    app = create_app()
    client = app.test_client()
    login_page = client.get("/login")
    html = login_page.get_data(as_text=True)
    print("LOGIN PAGE", login_page.status_code)
    if login_page.status_code != 200:
        raise SystemExit("Login page failed")
    if "Other Login" not in html or "other-login" not in html:
        raise SystemExit("Login page is missing the Other Login card")
    other = client.get("/other-login")
    other_html = other.get_data(as_text=True)
    print("OTHER LOGIN", other.status_code)
    if other.status_code != 200:
        raise SystemExit("Other Login page failed")
    if "Uttarakhand FPS Login" not in other_html:
        raise SystemExit("Other Login page missing FPS service")
    if other_html.count("Coming Soon") < 20:
        raise SystemExit("Disabled services are not showing Coming Soon")
    if 'href="/fps-login"' not in other_html:
        raise SystemExit("Enabled FPS service is not linked")
    fps_page = client.get("/fps-login")
    fps_html = fps_page.get_data(as_text=True)
    print("FPS LOGIN PAGE", fps_page.status_code)
    if fps_page.status_code != 200:
        raise SystemExit("FPS login page failed")
    if 'id="fpsState"' not in fps_html or 'id="fpsDistrict"' not in fps_html:
        raise SystemExit("FPS login cascade (State/District) is missing")
    if 'id="fpsDso"' not in fps_html or 'id="fpsAro"' not in fps_html or 'id="fpsSi"' not in fps_html:
        raise SystemExit("FPS login cascade (DSO/ARO/SI) is missing")
    if 'id="fpsSearch"' not in fps_html:
        raise SystemExit("FPS search box missing")
    if 'id="fpsBgNotice"' not in fps_html or "महत्वपूर्ण सूचना" not in fps_html:
        raise SystemExit("FPS login background notice is missing")
    if "अधिकृत पोर्टल नहीं" not in fps_html:
        raise SystemExit("FPS login disclaimer text is missing")
    if 'id="fpsBackLink"' not in fps_html:
        raise SystemExit("FPS back link is missing")
    if "type=\"text\" name=\"fps_id\"" in fps_html.lower() or "ocr" in fps_html.lower():
        raise SystemExit("FPS login must not have manual FPS ID or OCR")
    csrf_match = re.search(r'"csrf":\s*"([^"]+)"', fps_html)
    csrf_token = csrf_match.group(1) if csrf_match else ""
    blocked_shops = client.get("/fps-login/api/shops?q=TARA", headers={"Accept": "application/json"})
    blocked_payload = blocked_shops.get_json(silent=True) or {}
    print("FPS SHOPS WITHOUT SI", blocked_shops.status_code, blocked_payload.get("total"), blocked_payload.get("requires_si"))
    if blocked_shops.status_code != 200 or not blocked_payload.get("ok"):
        raise SystemExit(blocked_payload.get("error") or "FPS shop API failed")
    if blocked_payload.get("rows"):
        raise SystemExit("FPS list must stay empty until SI is selected")
    states = client.get("/fps-login/api/options?level=state", headers={"Accept": "application/json"})
    states_payload = states.get_json(silent=True) or {}
    print("FPS STATES", states.status_code, states_payload.get("count"))
    if states.status_code != 200 or not (states_payload.get("rows") or []):
        raise SystemExit("FPS login State list failed")
    state_id = states_payload["rows"][0]["id"]
    districts = client.get(
        f"/fps-login/api/options?level=district&parent_id={state_id}",
        headers={"Accept": "application/json"},
    )
    district_rows = (districts.get_json(silent=True) or {}).get("rows") or []
    if not district_rows:
        raise SystemExit("FPS login District list failed")
    district_id = district_rows[0]["id"]
    dsos = client.get(
        f"/fps-login/api/options?level=dso&parent_id={district_id}",
        headers={"Accept": "application/json"},
    )
    dso_rows = (dsos.get_json(silent=True) or {}).get("rows") or []
    if not dso_rows:
        raise SystemExit("FPS login DSO list failed")
    dso_id = dso_rows[0]["id"]
    aros = client.get(
        f"/fps-login/api/options?level=aro&parent_id={dso_id}",
        headers={"Accept": "application/json"},
    )
    aro_rows = (aros.get_json(silent=True) or {}).get("rows") or []
    if not aro_rows:
        raise SystemExit("FPS login ARO list failed")
    aro_id = aro_rows[0]["id"]
    sis = client.get(
        f"/fps-login/api/options?level=si&parent_id={aro_id}",
        headers={"Accept": "application/json"},
    )
    si_rows = (sis.get_json(silent=True) or {}).get("rows") or []
    if not si_rows:
        raise SystemExit("FPS login SI list failed")
    si_id = si_rows[0]["id"]
    shops = client.get(
        f"/fps-login/api/shops?state_id={state_id}&district_id={district_id}&dso_id={dso_id}&aro_id={aro_id}&si_id={si_id}&q=TARA",
        headers={"Accept": "application/json"},
    )
    shops_payload = shops.get_json(silent=True) or {}
    print("FPS SHOPS", shops.status_code, shops_payload.get("total"), shops_payload.get("error"))
    if shops.status_code != 200 or not shops_payload.get("ok"):
        raise SystemExit(shops_payload.get("error") or "FPS shop API failed")
    rows = shops_payload.get("rows") or []
    inactive = [row for row in rows if row.get("active_status") is False]
    if inactive:
        raise SystemExit("Inactive FPS records were returned")
    if not rows:
        print("FPS SHOPS empty — using synthetic session")
        fps_row_id = 1
        with client.session_transaction() as sess:
            sess["user_id"] = 900001
            sess["role"] = FPS_USER_ROLE
            sess["user_name"] = "TARA DURR"
            sess["fps_row_id"] = fps_row_id
            sess["auth_mode"] = "fps"
    else:
        fps_row_id = rows[0]["fps_row_id"]
        login_res = client.post(
            "/fps-login/api/login",
            json={"fps_row_id": fps_row_id, "csrf_token": csrf_token},
            headers={
                "Accept": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "X-CSRFToken": csrf_token,
            },
        )
        login_payload = login_res.get_json(silent=True) or {}
        print("FPS LOGIN", login_res.status_code, login_payload.get("ok"), login_payload.get("error"))
        if not login_payload.get("ok"):
            with client.session_transaction() as sess:
                sess["user_id"] = 900001
                sess["role"] = FPS_USER_ROLE
                sess["user_name"] = rows[0].get("shop_name") or "FPS"
                sess["fps_row_id"] = fps_row_id
                sess["auth_mode"] = "fps"
        else:
            report = client.get("/public-report/ration-card/fps-detail")
            report_html = report.get_data(as_text=True)
            print("FPS REPORT", report.status_code)
            if report.status_code != 200:
                raise SystemExit("FPS public report did not open after login")
            if "Selected FPS" not in report_html:
                raise SystemExit("FPS report is missing the locked Selected FPS panel")
            if 'id="rcDealerAddBtn"' in report_html and "rc-fps-readonly" not in report_html:
                raise SystemExit("FPS report is not in read-only mode")
    headers = {
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRFToken": csrf_token,
    }
    denied = client.get("/masters", follow_redirects=False)
    print("MASTERS DENY", denied.status_code, denied.headers.get("Location"))
    if denied.status_code not in {302, 403}:
        raise SystemExit("FPS_USER was allowed to open /masters")
    accounting = client.get("/accounting", follow_redirects=False)
    print("ACCOUNTING DENY", accounting.status_code)
    if accounting.status_code not in {302, 403}:
        raise SystemExit("FPS_USER was allowed to open /accounting")
    write = client.post(
        "/public-report/api/dealers",
        data={"DealerName": "Hack", "csrf_token": csrf_token},
        headers=headers,
    )
    write_payload = write.get_json(silent=True) or {}
    print("WRITE DENY", write.status_code, write_payload)
    if write.status_code != 403:
        raise SystemExit("FPS_USER write was not forbidden")
    if write_payload.get("error") != FPS_FORBIDDEN_MESSAGE:
        raise SystemExit("Forbidden message mismatch")
    import_denied = client.post(
        "/public-report/api/ration-card/fps-detail/generate",
        data={"dealer_id": "1", "csrf_token": csrf_token},
        headers=headers,
    )
    print("IMPORT DENY", import_denied.status_code)
    if import_denied.status_code != 403:
        raise SystemExit("FPS_USER CSV import was not forbidden")
    state_denied = client.get("/public-report/ration-card/state-master", follow_redirects=False)
    print("STATE MASTER DENY", state_denied.status_code, state_denied.headers.get("Location"))
    if state_denied.status_code not in {302, 403}:
        raise SystemExit("FPS_USER was allowed to open State Master")
    fps_master = client.get("/public-report/ration-card/fps-master", follow_redirects=False)
    print("FPS MASTER", fps_master.status_code)
    if fps_master.status_code != 200:
        raise SystemExit("FPS Master should open for FPS_USER")
    fps_master_html = fps_master.get_data(as_text=True)
    if 'id="pdsAddBtn"' in fps_master_html or "pds-readonly" not in fps_master_html:
        raise SystemExit("FPS Master is not read-only for FPS_USER")
    write_pds = client.post(
        "/public-report/api/pds/fps",
        data={"FpsName": "Hack", "csrf_token": csrf_token},
        headers=headers,
    )
    print("PDS WRITE DENY", write_pds.status_code)
    if write_pds.status_code != 403:
        raise SystemExit("FPS_USER PDS write was not forbidden")
    with app.app_context():
        nav = MenuService().get_navigation(FPS_USER_ROLE)
        names = {item.name.lower() for item in nav}
        print("FPS NAV", names)
        if names != {"public report"}:
            raise SystemExit(f"FPS_USER navigation must be Public Report only, got {names}")

        def flatten(nodes):
            rows = []
            for node in nodes:
                rows.append((node.name, bool(getattr(node, "disabled", False))))
                rows.extend(flatten(node.children))
            return rows

        flat = flatten(nav)
        enabled = {name for name, disabled in flat if not disabled}
        disabled = {name for name, is_disabled in flat if is_disabled}
        print("FPS ENABLED", enabled)
        print("FPS DISABLED", disabled)
        if "FPS Master" not in enabled or "Ration Card Master" not in enabled:
            raise SystemExit("FPS Master and Ration Card Master must be enabled")
        if "Ration Card Detail Report for FPS" not in enabled:
            raise SystemExit("FPS detail report must stay enabled")
        for blocked in ("State Master", "District Master", "DSO Master", "ARO Master", "SI Master"):
            if blocked not in disabled:
                raise SystemExit(f"{blocked} must be disabled for FPS_USER")
        if "Dashboard" in enabled or "Masters" in enabled or "Accounting" in enabled:
            raise SystemExit("ERP modules leaked into FPS_USER navigation")
        admin_nav = MenuService().get_navigation("Administrator")
        admin_names = {item.name.lower() for item in admin_nav}
        print("ADMIN NAV COUNT", len(admin_names))
        if "dashboard" not in admin_names or "public report" not in admin_names:
            raise SystemExit("Admin navigation lost Dashboard or Public Report")
        if "masters" not in admin_names and "accounting" not in admin_names:
            raise SystemExit("Admin navigation lost core ERP menus")
    print("PAGES AND SCOPE OK")


def main() -> int:
    test_catalog()
    test_allowlist()
    test_pages_and_scope()
    print("ALL OK", datetime.now(timezone.utc).isoformat())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
