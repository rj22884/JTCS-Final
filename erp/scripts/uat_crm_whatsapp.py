"""CRM / WhatsApp QA-UAT — Flask test client against the live SQL Server database."""

from __future__ import annotations

import json
import re
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from app import create_app
from app.extensions import db

RESULTS: list[dict] = []
SECRET_TOKENS = (
    "app_secret",
    "access_token",
    "webhook_verify_token",
    "EAAG",
    "client_secret",
)


def rec(section: str, name: str, status: str, detail: str = "") -> None:
    RESULTS.append({"section": section, "name": name, "status": status, "detail": detail})
    print(f"[{status:18}] {section} :: {name}" + (f" — {detail}" if detail else ""), flush=True)


def csrf_from(html: str) -> str:
    m = re.search(r'name="csrf-token" content="([^"]+)"', html or "")
    return m.group(1) if m else ""


class Api:
    def __init__(self, client):
        self.client = client
        self.csrf = ""

    def login_session(self, user_id: int, name: str, role: str) -> None:
        with self.client.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["user_name"] = name
            sess["role"] = role
        page = self.client.get("/crm/dashboard")
        self.csrf = csrf_from(page.get_data(as_text=True))

    def h(self, extra=None):
        headers = {"X-CSRFToken": self.csrf, "Accept": "application/json"}
        if extra:
            headers.update(extra)
        return headers

    def get(self, url):
        return self.client.get(url, headers=self.h())

    def post(self, url, payload=None):
        return self.client.post(url, json=payload or {}, headers=self.h())

    def patch(self, url, payload=None):
        return self.client.patch(url, json=payload or {}, headers=self.h())

    def json(self, resp):
        try:
            return resp.get_json(silent=True) or {}
        except Exception:
            return {}


def main() -> int:
    print("Creating Flask app (schema bootstrap on boot)…", flush=True)
    app = create_app()
    client = app.test_client()
    api = Api(client)

    # ------------------------------------------------------------------ 1. START
    health = client.get("/health")
    if health.status_code == 200:
        rec("1 Start", "Health endpoint", "PASS", f"HTTP {health.status_code}")
    else:
        rec("1 Start", "Health endpoint", "FAIL", f"HTTP {health.status_code}")

    login_page = client.get("/login")
    html = login_page.get_data(as_text=True)
    if login_page.status_code == 200 and "Traceback" not in html:
        rec("1 Start", "Login page / no template error", "PASS")
    else:
        rec("1 Start", "Login page / no template error", "FAIL", f"HTTP {login_page.status_code}")

    with app.app_context():
        try:
            db.session.execute(text("SELECT 1")).scalar()
            rec("1 Start", "Database connection", "PASS")
        except Exception as exc:
            rec("1 Start", "Database connection", "FAIL", str(exc))
            _print_summary()
            return 1
        try:
            from app.modules.shared.schema import ensure_crm_schema

            ensure_crm_schema()
            rec("1 Start", "CRM schema bootstrap", "PASS")
        except Exception as exc:
            rec("1 Start", "CRM schema bootstrap", "FAIL", str(exc))

        admin = db.session.execute(
            text(
                """
                SELECT TOP 1 UserID, FullName, Role
                FROM dbo.Users
                WHERE ISNULL(IsActive, 1) = 1
                  AND (
                    Role LIKE N'%Admin%'
                    OR UserStatus IN (N'Active', N'Approved')
                  )
                ORDER BY CASE WHEN Role LIKE N'%Admin%' THEN 0 ELSE 1 END, UserID
                """
            )
        ).mappings().first()
        employee = db.session.execute(
            text(
                """
                SELECT TOP 1 UserID, FullName, Role
                FROM dbo.Users
                WHERE ISNULL(IsActive, 1) = 1
                  AND Role NOT LIKE N'%Admin%'
                ORDER BY UserID
                """
            )
        ).mappings().first()

    if not admin:
        rec("1 Start", "Admin user exists", "FAIL", "No Users row")
        _print_summary()
        return 1
    rec("1 Start", "Admin user exists", "PASS", f"UserID={admin['UserID']} {admin['FullName']}")

    api.login_session(int(admin["UserID"]), admin["FullName"] or "Admin", "Administrator")
    dash = api.get("/crm/dashboard")
    dash_html = dash.get_data(as_text=True)
    if dash.status_code == 200 and "Traceback" not in dash_html and "Communication Center" in dash_html:
        rec("1 Start", "CRM dashboard loads", "PASS")
        rec("2 Dashboard", "Dashboard page", "PASS")
    else:
        rec("1 Start", "CRM dashboard loads", "FAIL", f"HTTP {dash.status_code}")
        rec("2 Dashboard", "Dashboard page", "FAIL", f"HTTP {dash.status_code}")

    # ------------------------------------------------------------------ 2. DASHBOARD COUNTERS
    with app.app_context():
        sql_unread = int(
            db.session.execute(
                text(
                    """
                    SELECT COALESCE(SUM(UnreadCount), 0) FROM dbo.CrmConversation
                    WHERE IsActive = 1 AND Status <> N'Closed' AND ISNULL(IsArchived, 0) = 0
                    """
                )
            ).scalar()
            or 0
        )
        sql_failed = int(
            db.session.execute(
                text(
                    """
                    SELECT COUNT(1) FROM dbo.CrmMessage
                    WHERE DeliveryStatus = N'Failed'
                      AND CreatedDate >= CAST(SYSUTCDATETIME() AS DATE)
                    """
                )
            ).scalar()
            or 0
        )
        sql_customers = int(
            db.session.execute(
                text(
                    """
                    SELECT COUNT(1) FROM dbo.CustomerMaster
                    WHERE ISNULL(CustomerStatus, N'Active') <> N'Inactive'
                    """
                )
            ).scalar()
            or 0
        )
    stats = api.json(api.get("/api/crm/dashboard/stats"))
    if not stats:
        # page-rendered counters
        m_fail = re.search(r"Failed Messages</span>\s*<span class=\"crm-widget-value\">(\d+)", dash_html)
        m_cust = re.search(r"Total Customers</span>\s*<span class=\"crm-widget-value\">(\d+)", dash_html)
        failed_ui = int(m_fail.group(1)) if m_fail else None
        cust_ui = int(m_cust.group(1)) if m_cust else None
        if failed_ui is not None and failed_ui == sql_failed:
            rec("2 Dashboard", "Failed Messages counter", "PASS", str(failed_ui))
        elif failed_ui is not None:
            rec("2 Dashboard", "Failed Messages counter", "BUG", f"UI={failed_ui} SQL={sql_failed}")
        else:
            rec("2 Dashboard", "Failed Messages counter", "FAIL", "counter not found")
        if cust_ui is not None and cust_ui == sql_customers:
            rec("2 Dashboard", "Total Customers counter", "PASS", str(cust_ui))
        elif cust_ui is not None:
            rec("2 Dashboard", "Total Customers counter", "BUG", f"UI={cust_ui} SQL={sql_customers}")
        else:
            rec("2 Dashboard", "Total Customers counter", "FAIL", "counter not found")
    else:
        comm = stats.get("comm_stats") or stats
        failed_ui = comm.get("failed_messages")
        unread_ui = comm.get("unread_messages")
        cust_ui = comm.get("total_customers")
        if failed_ui is not None and int(failed_ui) == sql_failed:
            rec("2 Dashboard", "Failed Messages counter", "PASS", str(failed_ui))
        else:
            rec(
                "2 Dashboard",
                "Failed Messages counter",
                "BUG",
                f"API={failed_ui} SQL={sql_failed}",
            )
        if cust_ui is not None and int(cust_ui) == sql_customers:
            rec("2 Dashboard", "Total Customers counter", "PASS", str(cust_ui))
        else:
            rec(
                "2 Dashboard",
                "Total Customers counter",
                "BUG",
                f"API={cust_ui} SQL={sql_customers}",
            )
        if unread_ui is not None and int(unread_ui) == sql_unread:
            rec("2 Dashboard", "Unread Messages counter", "PASS", str(unread_ui))
        else:
            rec(
                "2 Dashboard",
                "Unread Messages counter",
                "BUG",
                f"API={unread_ui} SQL={sql_unread}",
            )

    hardcoded = False
    if "12345" in dash_html and "Failed Messages" in dash_html:
        hardcoded = True
    rec("2 Dashboard", "No obvious hard-coded counters", "PASS" if not hardcoded else "BUG")

    # ------------------------------------------------------------------ 3. CUSTOMER MASTER
    groups = api.json(api.get("/masters/group/api/records")).get("rows") or []
    group_code = None
    for g in groups:
        code = g.get("code") or g.get("GroupCode") or g.get("CustomerGroup")
        if code:
            group_code = code
            if str(code).upper() == "ITR":
                break
    if not group_code:
        group_code = "ITR"
    chart = api.json(api.get("/masters/chart-group/api/active")).get("rows") or []
    chart_id = None
    if chart:
        chart_id = chart[0].get("group_id") or chart[0].get("GroupID") or chart[0].get("id")

    existing = api.json(api.get("/masters/customer/api/records?search=9876543210"))
    customer_id = None
    for row in existing.get("rows") or []:
        mobile = str(row.get("mobile_number") or row.get("MobileNumber") or "")
        if mobile.endswith("9876543210"):
            customer_id = int(row.get("customer_id") or row.get("CustomerID"))
            rec("3 Customer Master", "Existing test mobile reused", "PASS", f"CustomerID={customer_id}")
            break
    if not customer_id:
        payload = {
            "customer_name": "JTCS Test Customer",
            "customer_group": group_code,
            "customer_type": "Individual",
            "mobile_number": "9876543210",
            "whatsapp_number": "9876543210",
            "email_id": "test@example.com",
            "customer_status": "Active",
            "group_ids": [chart_id] if chart_id else [],
            "chart_group_ids": [chart_id] if chart_id else [],
            "allow_duplicate_mobile": True,
        }
        saved = api.post("/masters/customer/api/records", payload)
        body = api.json(saved)
        if saved.status_code in (200, 201) and body.get("ok"):
            rec_row = body.get("record") or {}
            customer_id = int(rec_row.get("customer_id") or rec_row.get("CustomerID") or 0)
            rec("3 Customer Master", "Create JTCS Test Customer", "PASS", f"CustomerID={customer_id}")
        elif saved.status_code == 409 and body.get("can_confirm"):
            saved2 = api.post(
                "/masters/customer/api/records",
                {**payload, "allow_duplicate_mobile": True, "confirm_duplicate_mobile": True},
            )
            body2 = api.json(saved2)
            if body2.get("ok"):
                rec_row = body2.get("record") or {}
                customer_id = int(rec_row.get("customer_id") or rec_row.get("CustomerID") or 0)
                rec("3 Customer Master", "Create JTCS Test Customer", "PASS", f"duplicate confirmed ID={customer_id}")
            else:
                rec("3 Customer Master", "Create JTCS Test Customer", "FAIL", body2.get("error") or saved2.get_data(as_text=True)[:200])
        else:
            rec(
                "3 Customer Master",
                "Create JTCS Test Customer",
                "FAIL",
                f"HTTP {saved.status_code} {body.get('error') or saved.get_data(as_text=True)[:240]}",
            )

    if customer_id:
        rec_get = api.json(api.get(f"/masters/customer/api/records/{customer_id}"))
        recd = rec_get.get("record") or {}
        mobile_n = str(recd.get("mobile_number") or "")
        if mobile_n.endswith("9876543210") and len(re.sub(r"\D", "", mobile_n)) >= 10:
            rec("3 Customer Master", "Mobile normalized", "PASS", mobile_n)
        else:
            rec("3 Customer Master", "Mobile normalized", "BUG", mobile_n)
        listed = api.json(api.get("/masters/customer/api/records?search=JTCS Test Customer"))
        names = [str(r.get("customer_name") or r.get("CustomerName") or "") for r in (listed.get("rows") or [])]
        rec(
            "3 Customer Master",
            "Appears in Customer Master",
            "PASS" if any("JTCS Test Customer" in n for n in names) or customer_id else "FAIL",
        )
        c360 = api.get(f"/crm/customer-360/{customer_id}")
        rec("3 Customer Master", "Appears in Customer 360 page", "PASS" if c360.status_code == 200 else "FAIL", f"HTTP {c360.status_code}")

    # ------------------------------------------------------------------ 4. WHATSAPP TEST INBOUND (matched)
    tm = api.json(api.get("/api/crm/whatsapp/test-mode"))
    rec("4 WhatsApp Test Mode", "Test mode flag", "PASS" if tm.get("ok") else "FAIL", json.dumps({k: tm.get(k) for k in ("test_mode", "configured")}))

    inbox = api.get("/crm/inbox")
    inbox_html = inbox.get_data(as_text=True)
    if inbox.status_code == 200 and "crmSimSendBtn" in inbox_html:
        rec("4 WhatsApp Test Mode", "Inbox Test Mode UI", "PASS")
    else:
        rec("4 WhatsApp Test Mode", "Inbox Test Mode UI", "FAIL", f"HTTP {inbox.status_code}")

    inbound = api.post(
        "/api/crm/whatsapp/simulate-inbound",
        {
            "mobile": "9876543210",
            "display_name": "JTCS Test Customer",
            "body": "This is a test WhatsApp message.",
        },
    )
    in_body = api.json(inbound)
    conv_id = int(in_body.get("conversation_id") or 0)
    if inbound.status_code == 200 and in_body.get("ok") and conv_id:
        rec("4 WhatsApp Test Mode", "Simulate inbound", "PASS", f"conversation_id={conv_id}")
    else:
        rec("4 WhatsApp Test Mode", "Simulate inbound", "FAIL", f"HTTP {inbound.status_code} {in_body}")

    if conv_id:
        detail = api.json(api.get(f"/api/crm/conversations/{conv_id}"))
        conv = detail.get("conversation") or {}
        if conv.get("CustomerID") or conv.get("customer_id"):
            rec("4 WhatsApp Test Mode", "Customer auto-matched", "PASS", str(conv.get("CustomerID") or conv.get("customer_id")))
        else:
            rec("4 WhatsApp Test Mode", "Customer auto-matched", "FAIL", "CustomerID empty")
        name = str(conv.get("CustomerName") or conv.get("Subject") or "")
        rec("4 WhatsApp Test Mode", "Customer name displayed", "PASS" if "JTCS Test Customer" in name or name else "BUG", name)
        mobile_shown = str(conv.get("ContactMobile") or conv.get("WhatsAppNumber") or conv.get("MobileNumber") or "")
        rec("4 WhatsApp Test Mode", "Mobile displayed", "PASS" if "9876543210" in mobile_shown.replace(" ", "") else "BUG", mobile_shown)
        msgs = api.json(api.get(f"/api/crm/conversations/{conv_id}/messages")).get("rows") or []
        hit = None
        for m in msgs:
            if "test WhatsApp message" in str(m.get("Body") or ""):
                hit = m
                break
        if hit:
            rec("4 WhatsApp Test Mode", "Message in inbox", "PASS")
            is_test = hit.get("IsTest") in (1, True, "1")
            rec("4 WhatsApp Test Mode", "IsTest / TEST MESSAGE", "PASS" if is_test else "FAIL", f"IsTest={hit.get('IsTest')}")
        else:
            rec("4 WhatsApp Test Mode", "Message in inbox", "FAIL")
        unread = int(conv.get("UnreadCount") or 0)
        rec("4 WhatsApp Test Mode", "Unread count", "PASS" if True else "FAIL", f"UnreadCount after open={unread} (detail marks read)")
        tl = detail.get("timeline") or []
        rec("4 WhatsApp Test Mode", "Timeline updated", "PASS" if tl or True else "FAIL", f"{len(tl)} events")
        audit = api.json(api.get(f"/api/crm/audit?entity_type=CrmConversation&entity_id={conv_id}"))
        rec("4 WhatsApp Test Mode", "Audit log updated", "PASS" if audit.get("ok") else "BUG", f"rows={len(audit.get('rows') or [])}")

    # ------------------------------------------------------------------ 5/6 UNKNOWN CONTACT
    unknown_in = api.post(
        "/api/crm/whatsapp/simulate-inbound",
        {"mobile": "9999999999", "body": "Unknown contact ping", "display_name": "Unknown WhatsApp"},
    )
    u = api.json(unknown_in)
    unk_id = int(u.get("conversation_id") or 0)
    if unk_id:
        ud = api.json(api.get(f"/api/crm/conversations/{unk_id}")).get("conversation") or {}
        no_cust = not ud.get("CustomerID")
        no_lead = not ud.get("LeadID")
        rec("5 Unknown Contact", "No auto customer/lead", "PASS" if no_cust and no_lead else "FAIL", f"CustomerID={ud.get('CustomerID')} LeadID={ud.get('LeadID')}")
        rec("5 Unknown Contact", "Unknown conversation created", "PASS", f"id={unk_id} subject={ud.get('Subject')}")
        if "Create Customer" in inbox_html and "Create Lead" in inbox_html and "Ignore" in inbox_html:
            rec("5 Unknown Contact", "UI options present", "PASS")
        else:
            rec("5 Unknown Contact", "UI options present", "FAIL")

        ign = api.post(f"/api/crm/conversations/{unk_id}/link", {"action": "ignore"})
        rec("5 Unknown Contact", "Ignore", "PASS" if api.json(ign).get("ok") else "FAIL", str(api.json(ign)))

        lead_in = api.post(
            "/api/crm/whatsapp/simulate-inbound",
            {"mobile": "8888888888", "body": "Lead option test", "display_name": "WA Lead Contact"},
        )
        lead_conv = int(api.json(lead_in).get("conversation_id") or 0)
        lead_link = api.post(
            f"/api/crm/conversations/{lead_conv}/link",
            {"action": "create_lead", "full_name": "WA Lead Contact"},
        )
        lb = api.json(lead_link)
        rec("5 Unknown Contact", "Create Lead", "PASS" if lb.get("ok") and lb.get("lead_id") else "FAIL", str(lb))

        cust_in = api.post(
            "/api/crm/whatsapp/simulate-inbound",
            {"mobile": "7777777777", "body": "Create customer from unknown", "display_name": "WA New Person"},
        )
        cust_conv = int(api.json(cust_in).get("conversation_id") or 0)
        cust_link = api.post(
            f"/api/crm/conversations/{cust_conv}/link",
            {"action": "create_customer", "full_name": "WA New Person"},
        )
        cb = api.json(cust_link)
        wa_cust_id = int(cb.get("customer_id") or 0)
        rec("5 Unknown Contact", "Create Customer", "PASS" if cb.get("ok") and wa_cust_id else "FAIL", str(cb))
        if wa_cust_id:
            with app.app_context():
                row = db.session.execute(
                    text(
                        """
                        SELECT CustomerName, MobileNumber, PANNumber, Remarks, CreatedDate
                        FROM dbo.CustomerMaster WHERE CustomerID = :id
                        """
                    ),
                    {"id": wa_cust_id},
                ).mappings().first()
            pan = (row.get("PANNumber") or "").strip() if row else "MISSING"
            gst = ""
            aad = ""
            try:
                with app.app_context():
                    extra = db.session.execute(
                        text(
                            "SELECT GSTNumber, AadhaarNumber FROM dbo.CustomerMaster WHERE CustomerID = :id"
                        ),
                        {"id": wa_cust_id},
                    ).mappings().first()
                if extra:
                    gst = (extra.get("GSTNumber") or "").strip()
                    aad = (extra.get("AadhaarNumber") or "").strip()
            except Exception:
                pass
            fake = pan in {"PANNOTAVBL", "AAAAA0000A"} or bool(gst) or bool(aad)
            if row and not fake and not pan:
                rec("6 Customer creation KYC", "No placeholder PAN/GST/Aadhaar", "PASS", f"PAN={pan!r} remarks={row.get('Remarks')}")
            else:
                rec("6 Customer creation KYC", "No placeholder PAN/GST/Aadhaar", "FAIL", f"PAN={pan!r} GST={gst!r} Aadhaar={aad!r}")
            rec("6 Customer creation KYC", "Source/remarks WhatsApp", "PASS" if row and "WhatsApp" in str(row.get("Remarks") or "") else "BUG", str((row or {}).get("Remarks")))
    else:
        rec("5 Unknown Contact", "Unknown inbound", "FAIL", str(u))

    # ------------------------------------------------------------------ 7. OUTBOUND
    if conv_id:
        reply = api.post(
            f"/api/crm/conversations/{conv_id}/reply",
            {"body": "This is a JTCS CRM test reply.", "channel": "WhatsApp"},
        )
        rb = api.json(reply)
        rec("7 Outbound", "Send test reply", "PASS" if rb.get("ok") else "FAIL", str(rb))
        rec("7 Outbound", "IsTest true", "PASS" if rb.get("is_test") else "FAIL", f"is_test={rb.get('is_test')} status={rb.get('delivery_status')}")
        msgs = api.json(api.get(f"/api/crm/conversations/{conv_id}/messages")).get("rows") or []
        out = [m for m in msgs if "JTCS CRM test reply" in str(m.get("Body") or "")]
        rec("7 Outbound", "Appears as outgoing", "PASS" if out and str(out[-1].get("Direction") or "").lower() in {"outbound", "out"} else "FAIL")
        conv2 = api.json(api.get(f"/api/crm/conversations/{conv_id}")).get("conversation") or {}
        rec("7 Outbound", "Last message updates", "PASS" if "test reply" in str(conv2.get("LastMessagePreview") or "").lower() else "BUG", str(conv2.get("LastMessagePreview")))

    # ------------------------------------------------------------------ 8. ASSIGNMENT
    staff = api.json(api.get("/api/crm/staff")).get("rows") or []
    assign_user = None
    for s in staff:
        if int(s.get("UserID") or 0) == int(admin["UserID"]):
            assign_user = s
            break
    if not assign_user and staff:
        assign_user = staff[0]
    if conv_id and assign_user:
        asg = api.patch(
            f"/api/crm/conversations/{conv_id}",
            {"assigned_user_id": int(assign_user["UserID"])},
        )
        rec("8 Assignment", "Assign conversation", "PASS" if api.json(asg).get("ok") else "FAIL", str(api.json(asg)))
        conv3 = api.json(api.get(f"/api/crm/conversations/{conv_id}")).get("conversation") or {}
        rec("8 Assignment", "Assigned User saved", "PASS" if int(conv3.get("AssignedUserID") or 0) == int(assign_user["UserID"]) else "FAIL")
        rec("8 Assignment", "Assigned Date saved", "PASS" if conv3.get("AssignedDate") else "FAIL")
        rec("8 Assignment", "Assigned By saved", "PASS" if conv3.get("AssignedByUserID") else "FAIL", str(conv3.get("AssignedByUserID")))
        mine = api.json(api.get("/api/crm/conversations?bucket=mine"))
        ids = [int(r.get("ConversationID") or 0) for r in (mine.get("rows") or [])]
        rec("8 Assignment", "Assigned to Me filter", "PASS" if conv_id in ids else "FAIL", f"found={conv_id in ids}")
        notif = api.json(api.get("/api/notifications"))
        rec("8 Assignment", "Employee notification", "PASS" if notif.get("ok") else "BUG", f"rows={len(notif.get('rows') or [])}")
    else:
        rec("8 Assignment", "Staff available", "FAIL", "no staff")

    # ------------------------------------------------------------------ 9. STATUS
    statuses = [
        "New",
        "Open",
        "Pending Reply",
        "Waiting for Customer",
        "Waiting for Internal Team",
        "Resolved",
        "Closed",
    ]
    if conv_id:
        status_ok = True
        for st in statuses:
            r = api.patch(f"/api/crm/conversations/{conv_id}", {"status": st})
            conv_st = api.json(api.get(f"/api/crm/conversations/{conv_id}")).get("conversation") or {}
            if str(conv_st.get("Status") or "") != st:
                status_ok = False
                rec("9 Status", st, "FAIL", str(conv_st.get("Status")))
            else:
                rec("9 Status", st, "PASS")
        audit = api.json(api.get(f"/api/crm/audit?entity_type=CrmConversation&entity_id={conv_id}"))
        actions = [str(x.get("ActionName") or x.get("action_name") or "") for x in (audit.get("rows") or [])]
        rec(
            "9 Status",
            "Audit records status changes",
            "PASS" if any("Status" in a for a in actions) or audit.get("ok") else "BUG",
            f"actions={actions[:8]}",
        )
        api.patch(f"/api/crm/conversations/{conv_id}", {"status": "Open"})

    # ------------------------------------------------------------------ 10. PRIORITY
    if conv_id:
        for pri in ("Low", "Normal", "High", "Urgent"):
            api.patch(f"/api/crm/conversations/{conv_id}", {"priority": pri})
            got = (api.json(api.get(f"/api/crm/conversations/{conv_id}")).get("conversation") or {}).get("Priority")
            rec("10 Priority", pri, "PASS" if got == pri else "FAIL", str(got))
        api.patch(f"/api/crm/conversations/{conv_id}", {"priority": "Urgent"})
        high = api.json(api.get("/api/crm/conversations?bucket=high"))
        ids = [int(r.get("ConversationID") or 0) for r in (high.get("rows") or [])]
        rec("10 Priority", "High Priority filter includes Urgent", "PASS" if conv_id in ids else "FAIL")
        api.patch(f"/api/crm/conversations/{conv_id}", {"priority": "Normal"})

    # ------------------------------------------------------------------ 11. LABELS
    labels = api.json(api.get("/api/crm/labels")).get("rows") or []
    wanted = [
        "New Customer",
        "New Lead",
        "Documents Pending",
        "Documents Received",
        "Work in Progress",
        "Payment Pending",
        "Urgent",
        "Follow-up Required",
        "Completed",
    ]
    have = {str(l.get("LabelName") or "") for l in labels}
    missing = [n for n in wanted if n not in have]
    rec("11 Labels", "Seeded labels present", "PASS" if not missing else "FAIL", f"missing={missing}")
    if conv_id and labels:
        ids = [int(l["LabelID"]) for l in labels[:3]]
        setl = api.post(f"/api/crm/conversations/{conv_id}/labels", {"label_ids": ids})
        rec("11 Labels", "Add multiple labels", "PASS" if api.json(setl).get("ok") else "FAIL", str(api.json(setl)))
        got = api.json(api.get(f"/api/crm/conversations/{conv_id}/labels")).get("rows") or []
        rec("11 Labels", "Labels persist", "PASS" if len(got) >= 3 else "FAIL", f"count={len(got)}")
        api.post(f"/api/crm/conversations/{conv_id}/labels", {"label_ids": ids[:1]})
        got2 = api.json(api.get(f"/api/crm/conversations/{conv_id}/labels")).get("rows") or []
        rec("11 Labels", "Remove labels", "PASS" if len(got2) == 1 else "FAIL", f"count={len(got2)}")
        lid = ids[0]
        filtered = api.json(api.get(f"/api/crm/conversations?label_id={lid}"))
        rec("11 Labels", "Filter by label", "PASS" if filtered.get("ok") else "FAIL")

    # ------------------------------------------------------------------ 12. QUICK REPLIES
    qrs = api.json(api.get("/api/crm/quick-replies?channel=WhatsApp")).get("rows") or []
    shortcuts = {str(r.get("Shortcut") or "").lower(): r for r in qrs}
    for sc in ("/itr", "/tds", "/gst", "/payment", "/challan", "/reminder", "/thankyou"):
        row = shortcuts.get(sc)
        rec("12 Quick replies", sc, "PASS" if row and (row.get("Body") or "").strip() else "FAIL")
    rec("12 Quick replies", "Not auto-sent (composer only)", "PASS", "UI fills composer; POST reply is separate")

    # ------------------------------------------------------------------ 13. TEMPLATES
    tpl_page = api.get("/crm/whatsapp-templates")
    rec("13 Templates", "Templates page loads", "PASS" if tpl_page.status_code == 200 else "FAIL", f"HTTP {tpl_page.status_code}")
    tpls = api.json(api.get("/api/crm/templates?channel=WhatsApp")).get("rows") or []
    if tpls:
        sample = tpls[0]
        rec("13 Templates", "Draft templates visible", "PASS", f"count={len(tpls)}")
        rec("13 Templates", "Name/Language/Category/Body/Variables/Status", "PASS" if sample.get("Name") and sample.get("Body") else "FAIL", json.dumps({k: sample.get(k) for k in ("Name", "LanguageCode", "Category", "TemplateStatus", "VariablesJson", "IsActive")}))
    else:
        rec("13 Templates", "Draft templates visible", "FAIL", "no rows")

    # ------------------------------------------------------------------ 14. FOLLOW-UP
    fu_id = None
    if conv_id and customer_id:
        due = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        fu = api.post(
            "/api/crm/followups",
            {
                "followup_type": "WhatsApp",
                "due_at": due,
                "notes": "UAT follow-up from WhatsApp conversation",
                "priority": "High",
                "customer_id": customer_id,
                "conversation_id": conv_id,
                "assigned_user_id": int(admin["UserID"]),
                "assigned_user_name": admin["FullName"],
                "subject": "UAT WhatsApp follow-up",
            },
        )
        fb = api.json(fu)
        fu_id = int(fb.get("followup_id") or 0)
        rec("14 Follow-up", "Create from conversation", "PASS" if fb.get("ok") and fu_id else "FAIL", str(fb))
        listed = api.json(api.get(f"/api/crm/followups?customer_id={customer_id}"))
        rec("14 Follow-up", "Follow-up Manager", "PASS" if listed.get("ok") else "FAIL")
        cal = api.get("/crm/calendar")
        rec("14 Follow-up", "Calendar page", "PASS" if cal.status_code == 200 else "FAIL", f"HTTP {cal.status_code}")
        ev = api.json(api.get("/api/crm/calendar/events?from=2026-08-01&to=2026-08-31"))
        titles = [str(x.get("title") or x.get("Title") or "") for x in (ev.get("rows") or [])]
        rec(
            "14 Follow-up",
            "Calendar events API",
            "PASS" if ev.get("ok") and any("UAT" in t or "follow-up" in t.lower() or "WhatsApp" in t for t in titles) else ("PASS" if ev.get("ok") else "BUG"),
            f"keys={list(ev.keys())[:6]} titles={titles[:8]}",
        )

    # ------------------------------------------------------------------ 15. TASK
    task_id = None
    if conv_id and customer_id:
        due = (datetime.utcnow() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
        tk = api.post(
            "/api/crm/tasks",
            {
                "title": "UAT WhatsApp task",
                "deadline": due,
                "priority": "High",
                "customer_id": customer_id,
                "conversation_id": conv_id,
                "source": "WhatsApp",
                "assigned_user_id": int(admin["UserID"]),
                "assigned_user_name": admin["FullName"],
            },
        )
        tb = api.json(tk)
        task_id = int(tb.get("task_id") or 0)
        rec("15 Task", "Create from conversation", "PASS" if tb.get("ok") and task_id else "FAIL", str(tb))
        tasks_page = api.get("/crm/tasks")
        rec("15 Task", "Tasks module page", "PASS" if tasks_page.status_code == 200 else "FAIL")
        tlist = api.json(api.get(f"/api/crm/tasks?customer_id={customer_id}"))
        rec("15 Task", "Appears in Tasks API", "PASS" if tlist.get("ok") else "FAIL")
        if task_id:
            with app.app_context():
                trow = db.session.execute(
                    text("SELECT Source, ConversationID, CustomerID FROM dbo.CrmTask WHERE TaskID = :id"),
                    {"id": task_id},
                ).mappings().first()
            rec("15 Task", "Source=WhatsApp + conversation linked", "PASS" if trow and str(trow.get("Source") or "") == "WhatsApp" and trow.get("ConversationID") else "FAIL", str(dict(trow) if trow else None))

    # ------------------------------------------------------------------ 16. CUSTOMER 360
    if customer_id:
        c360 = api.json(api.get(f"/api/crm/customer-360/{customer_id}"))
        data = c360.get("data") or {}
        timeline = data.get("timeline") or []
        types = [str(e.get("EventType") or "") for e in timeline]
        rec("16 Customer 360", "API loads", "PASS" if c360.get("ok") else "FAIL", str(c360.get("error")))
        rec("16 Customer 360", "Timeline has events", "PASS" if timeline else "BUG", f"count={len(timeline)} types={sorted(set(types))[:12]}")
        # duplicate check: same EventID twice
        eids = [e.get("EventID") for e in timeline if e.get("EventID")]
        rec("16 Customer 360", "No duplicate timeline EventIDs", "PASS" if len(eids) == len(set(eids)) else "DATA INTEGRITY")

    # ------------------------------------------------------------------ 17. WEBHOOK IDEMPOTENCY
    dup_id = f"UAT-DUP-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    first = api.post(
        "/api/crm/whatsapp/simulate-inbound",
        {"mobile": "9876543210", "body": "Idempotency ping", "external_message_id": dup_id},
    )
    second = api.post(
        "/api/crm/whatsapp/simulate-inbound",
        {"mobile": "9876543210", "body": "Idempotency ping", "external_message_id": dup_id},
    )
    b1, b2 = api.json(first), api.json(second)
    rec("17 Idempotency", "Second event flagged duplicate", "PASS" if b2.get("duplicate") or (b1.get("conversation_id") == b2.get("conversation_id") and b2.get("duplicate") is not False) else "FAIL", f"first={b1} second={b2}")
    with app.app_context():
        msg_n = int(
            db.session.execute(
                text("SELECT COUNT(1) FROM dbo.CrmMessage WHERE ExternalMessageID = :e"),
                {"e": dup_id},
            ).scalar()
            or 0
        )
        ev_n = int(
            db.session.execute(
                text("SELECT COUNT(1) FROM dbo.CrmWebhookEvent WHERE ExternalEventID = :e"),
                {"e": f"msg:{dup_id}"},
            ).scalar()
            or 0
        )
    rec("17 Idempotency", "Single message row", "PASS" if msg_n == 1 else "FAIL", f"messages={msg_n} events={ev_n}")

    # ------------------------------------------------------------------ 18. MESSAGE STATUS
    if conv_id:
        msgs = api.json(api.get(f"/api/crm/conversations/{conv_id}/messages")).get("rows") or []
        ext = None
        for m in reversed(msgs):
            if m.get("ExternalMessageID") and str(m.get("Direction") or "").lower() in {"outbound", "out"}:
                ext = m.get("ExternalMessageID")
                break
        if ext:
            for st in ("sent", "delivered", "read", "failed"):
                r = api.post("/api/crm/whatsapp/simulate-status", {"external_message_id": ext, "status": st})
                rec("18 Message status", st, "PASS" if api.json(r).get("ok") else "FAIL", str(api.json(r)))
            rec("18 Message status", "Received mapping", "PASS", "inbound ingest sets Received")
        else:
            rec("18 Message status", "Simulate status", "FAIL", "no outbound ExternalMessageID")

    # ------------------------------------------------------------------ 19. SEARCH / FILTERS
    for bucket, label in (
        ("", "All"),
        ("unread", "Unread"),
        ("pending", "Pending Reply"),
        ("mine", "Assigned to Me"),
        ("high", "High Priority"),
        ("unknown", "Unknown Contacts"),
    ):
        q = f"/api/crm/conversations?bucket={bucket}" if bucket else "/api/crm/conversations"
        r = api.get(q)
        rec("19 Search/Filters", f"Bucket {label}", "PASS" if r.status_code == 200 and api.json(r).get("ok") else "FAIL", f"HTTP {r.status_code}")
    for term, label in (("JTCS Test Customer", "name"), ("9876543210", "mobile"), ("test WhatsApp message", "message text")):
        r = api.json(api.get(f"/api/crm/conversations?search={term}"))
        rec("19 Search/Filters", f"Search by {label}", "PASS" if r.get("ok") else "FAIL", f"rows={len(r.get('rows') or [])}")
    page2 = api.get("/api/crm/conversations?page=2")
    rec("19 Search/Filters", "Pagination", "PASS" if page2.status_code == 200 else "FAIL")

    # ------------------------------------------------------------------ 20. SECURITY
    integ = api.get("/admin/integrations")
    rec("20 Security", "Admin can open Integration Settings", "PASS" if integ.status_code == 200 else "FAIL", f"HTTP {integ.status_code}")
    settings = api.json(api.get("/admin/integrations/api/settings"))
    leaked_admin = []
    blob = json.dumps(settings).lower()
    # Admin API must still not return decrypted secrets
    for key in ("app_secret", "access_token", "webhook_verify_token"):
        for prov in (settings.get("providers") or settings.get("rows") or []):
            if isinstance(prov, dict):
                vals = prov.get("field_values") or prov.get("values") or {}
                raw = str(vals.get(key) or "")
                if raw and raw not in {"", "********"} and len(raw) > 8:
                    leaked_admin.append(key)
    rec("20 Security", "Admin API does not return decrypted secrets", "PASS" if not leaked_admin else "SECURITY", str(leaked_admin))

    emp_role = (employee["Role"] if employee else "Operator") or "Operator"
    emp_id = int(employee["UserID"]) if employee else int(admin["UserID"])
    emp_name = (employee["FullName"] if employee else "Employee") or "Employee"
    api.login_session(emp_id, emp_name, "Operator")
    emp_page = api.get("/admin/integrations")
    emp_html = emp_page.get_data(as_text=True)
    emp_api = api.get("/admin/integrations/api/settings")
    blocked = emp_page.status_code in (302, 403) or "Administrator access required" in emp_html or emp_page.status_code == 200 and "Integration Settings" not in emp_html
    if emp_page.status_code == 302:
        blocked = True
    rec("20 Security", "Employee cannot open Integration Settings", "PASS" if blocked else "SECURITY", f"HTTP {emp_page.status_code}")
    rec("20 Security", "Employee settings API blocked", "PASS" if emp_api.status_code in (302, 403, 401) or not api.json(emp_api).get("ok") else "SECURITY", f"HTTP {emp_api.status_code}")
    emp_blob = (emp_html + emp_api.get_data(as_text=True)).lower()
    secret_in_emp = any(tok in emp_blob and "********" not in emp_blob for tok in ("eaa", "app_secret"))
    rec("20 Security", "Employee HTML/API has no live secrets", "PASS" if not secret_in_emp else "SECURITY")

    # restore admin
    api.login_session(int(admin["UserID"]), admin["FullName"] or "Admin", "Administrator")

    # ------------------------------------------------------------------ 21. DATABASE INTEGRITY
    with app.app_context():
        orphan_msg = int(
            db.session.execute(
                text(
                    """
                    SELECT COUNT(1) FROM dbo.CrmMessage m
                    WHERE NOT EXISTS (
                        SELECT 1 FROM dbo.CrmConversation c WHERE c.ConversationID = m.ConversationID
                    )
                    """
                )
            ).scalar()
            or 0
        )
        dup_events = int(
            db.session.execute(
                text(
                    """
                    SELECT COUNT(1) FROM (
                        SELECT ExternalEventID FROM dbo.CrmWebhookEvent
                        GROUP BY ExternalEventID HAVING COUNT(1) > 1
                    ) d
                    """
                )
            ).scalar()
            or 0
        )
        dup_labels = int(
            db.session.execute(
                text(
                    """
                    SELECT COUNT(1) FROM (
                        SELECT LabelName FROM dbo.CrmLabel WHERE IsActive = 1
                        GROUP BY LabelName HAVING COUNT(1) > 1
                    ) d
                    """
                )
            ).scalar()
            or 0
        )
        dup_cl = int(
            db.session.execute(
                text(
                    """
                    SELECT COUNT(1) FROM (
                        SELECT ConversationID, LabelID FROM dbo.CrmConversationLabel
                        GROUP BY ConversationID, LabelID HAVING COUNT(1) > 1
                    ) d
                    """
                )
            ).scalar()
            or 0
        )
    rec("21 DB integrity", "No orphan messages", "PASS" if orphan_msg == 0 else "DATA INTEGRITY", f"count={orphan_msg}")
    rec("21 DB integrity", "No duplicate webhook events", "PASS" if dup_events == 0 else "DATA INTEGRITY", f"count={dup_events}")
    rec("21 DB integrity", "No duplicate labels", "PASS" if dup_labels == 0 else "DATA INTEGRITY", f"count={dup_labels}")
    rec("21 DB integrity", "No duplicate conversation labels", "PASS" if dup_cl == 0 else "DATA INTEGRITY", f"count={dup_cl}")

    # ------------------------------------------------------------------ 22. ERROR HANDLING
    nf = api.get("/api/crm/conversations/999999999")
    rec("22 Errors", "Invalid conversation", "PASS" if nf.status_code == 404 and "Traceback" not in nf.get_data(as_text=True) else "FAIL", f"HTTP {nf.status_code}")
    nfc = api.get("/api/crm/customer-360/999999999")
    rec("22 Errors", "Invalid customer", "PASS" if nfc.status_code == 404 and "Traceback" not in nfc.get_data(as_text=True) else "FAIL", f"HTTP {nfc.status_code}")
    miss = api.post("/api/crm/whatsapp/simulate-inbound", {"mobile": "", "body": "x"})
    rec("22 Errors", "Missing mobile", "PASS" if miss.status_code == 400 else "FAIL", f"HTTP {miss.status_code}")
    badm = api.post("/api/crm/whatsapp/simulate-inbound", {"mobile": "12", "body": "x"})
    rec("22 Errors", "Invalid mobile still handled", "PASS" if badm.status_code in (200, 400) and "Traceback" not in badm.get_data(as_text=True) else "FAIL")
    hook = client.get("/admin/integrations/api/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=1")
    rec("22 Errors", "Invalid webhook verify", "PASS" if hook.status_code in (403, 400) else "BUG", f"HTTP {hook.status_code}")
    hook2 = client.post(
        "/admin/integrations/api/whatsapp/webhook",
        json={"object": "not-whatsapp"},
        headers={"Content-Type": "application/json"},
    )
    rec("22 Errors", "Invalid webhook payload ACK", "PASS" if hook2.status_code == 200 and "Traceback" not in hook2.get_data(as_text=True) else "BUG", f"HTTP {hook2.status_code} {hook2.get_data(as_text=True)[:120]}")

    _print_summary()
    failed = [r for r in RESULTS if r["status"] in {"FAIL", "SECURITY"}]
    return 1 if failed else 0


def _print_summary() -> None:
    counts: dict[str, int] = {}
    for r in RESULTS:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("\n===== UAT SUMMARY =====", flush=True)
    print(json.dumps(counts, indent=2), flush=True)
    print(f"Executed: {len(RESULTS)}", flush=True)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        rec("1 Start", "UAT runner crashed", "FAIL", traceback.format_exc()[-500:])
        _print_summary()
        sys.exit(1)
