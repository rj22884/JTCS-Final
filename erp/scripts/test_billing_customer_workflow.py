"""
Same Customer / Other Customer billing workflow tests (Misc + follow-up).

Run:
    cd erp
    .\\.venv\\Scripts\\python.exe scripts\\test_billing_customer_workflow.py
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def run_tests() -> int:
    from app import create_app
    from app.repositories.transaction_repository import MasterRepository
    from app.services.followup_service import FollowupService
    from app.services.others_income_expense_service import OthersIncomeExpenseService

    app = create_app()
    failures: list[str] = []
    suffix = uuid.uuid4().hex[:8]

    def ok(name: str) -> None:
        print(f"  OK  {name}")

    def fail(name: str, detail: str) -> None:
        failures.append(f"{name}: {detail}")
        print(f"  FAIL {name}: {detail}")

    with app.app_context():
        customers = MasterRepository().list_customers()
        if len(customers) < 2:
            fail("setup", "Need at least two customers")
            return 1
        c1 = int(customers[0].CustomerID)
        c2 = int(customers[1].CustomerID)

        for module in ("ITR", "GST", "TDS", "DSC"):
            svc = FollowupService(module)

            # No billing choice and no invoice -> empty type, follow-up customer
            btype, bid = svc._resolve_billing_customer(
                {},
                followup_customer_id=c1,
                invoice_checked=False,
            )
            if btype != "" or bid != c1:
                fail(f"{module} no choice", f"type={btype} id={bid}")
            else:
                ok(f"{module} no billing choice without invoice is optional")

            # Invoice linked / stage requires Same or Other
            try:
                svc._resolve_billing_customer(
                    {},
                    followup_customer_id=c1,
                    invoice_checked=True,
                )
                fail(f"{module} invoice requires choice", "no error")
            except ValueError as exc:
                if "Same Customer" in str(exc) or "Other Customer" in str(exc):
                    ok(f"{module} invoice/stage requires Same or Other")
                else:
                    fail(f"{module} invoice requires choice", str(exc))

            # Same Customer without invoice stage still allowed when chosen
            btype, bid = svc._resolve_billing_customer(
                {"billing_type": "SAME_CUSTOMER"},
                followup_customer_id=c1,
                invoice_checked=False,
            )
            if btype != "SAME_CUSTOMER" or bid != c1:
                fail(f"{module} same customer", f"type={btype} id={bid}")
            else:
                ok(f"{module} Same Customer maps to follow-up customer")

            # Other Customer
            btype, bid = svc._resolve_billing_customer(
                {"billing_type": "OTHER_CUSTOMER", "billing_customer_id": c2},
                followup_customer_id=c1,
                invoice_checked=False,
            )
            if btype != "OTHER_CUSTOMER" or bid != c2:
                fail(f"{module} other customer", f"type={btype} id={bid}")
            else:
                ok(f"{module} Other Customer maps to billing customer")

            # Invalid other customer rejected
            try:
                svc._resolve_billing_customer(
                    {"billing_type": "OTHER_CUSTOMER", "billing_customer_id": 0},
                    followup_customer_id=c1,
                    invoice_checked=True,
                )
                fail(f"{module} invalid billing", "accepted 0")
            except ValueError:
                ok(f"{module} rejects invalid Other Customer id")

            # Missing follow-up customer rejected for Same
            try:
                svc._resolve_billing_customer(
                    {"billing_type": "SAME_CUSTOMER"},
                    followup_customer_id=0,
                    invoice_checked=False,
                )
                fail(f"{module} missing followup customer", "accepted")
            except ValueError:
                ok(f"{module} rejects Same Customer without follow-up customer")

        # Misc reassign rejects invalid billing customer
        misc = OthersIncomeExpenseService()
        try:
            misc.reassign_misc_invoice_customer(999999991, 0)
            fail("misc invalid billing", "accepted")
        except ValueError as exc:
            if "Billing Customer" in str(exc) or "not found" in str(exc).lower():
                ok("Misc reassign rejects invalid billing customer id")
            else:
                fail("misc invalid billing", str(exc))

        try:
            misc.reassign_misc_invoice_customer(999999991, c1)
            fail("misc missing entry", "accepted")
        except ValueError as exc:
            if "not found" in str(exc).lower():
                ok("Misc reassign rejects missing entry")
            else:
                fail("misc missing entry", str(exc))

        # Frontend markers: Invoice checkbox removed; billing wrap present for Misc template
        misc_html = (
            ROOT / "app" / "templates" / "others" / "income_expense_activity.html"
        ).read_text(encoding="utf-8")
        if "oieInvoiceCheck" in misc_html:
            fail("misc template", "oieInvoiceCheck still present")
        elif "oieBillingSame" not in misc_html or "oieCreateInvoiceBtn" not in misc_html:
            fail("misc template", "billing/create controls missing")
        else:
            ok("Misc template has no Invoice checkbox; Same/Other + Create Invoice remain")

        fu_html = (ROOT / "app" / "templates" / "followup" / "activity.html").read_text(
            encoding="utf-8"
        )
        if "stage.stage_code == 'invoice'" not in fu_html or "d-none" not in fu_html:
            fail("followup template", "invoice stage not hidden")
        elif "fuBillingSame" not in fu_html:
            fail("followup template", "Same Customer missing")
        else:
            ok("Follow-up template hides Invoice stage checkbox; Same/Other remain")

        misc_js = (ROOT / "app" / "static" / "js" / "income_expense_activity.js").read_text(
            encoding="utf-8"
        )
        if "oieInvoiceCheck" in misc_js:
            fail("misc js", "still references oieInvoiceCheck")
        elif "onMiscCustomerChanged" not in misc_js:
            fail("misc js", "customer change handler missing")
        else:
            ok("Misc JS shows billing from customer select (no Invoice checkbox)")

        fu_js = (ROOT / "app" / "static" / "js" / "followup_activity.js").read_text(
            encoding="utf-8"
        )
        if "onFollowupCustomerChanged" not in fu_js:
            fail("followup js", "customer change handler missing")
        elif "isStageChecked(\"invoice\") || creatingInvoice" in fu_js:
            fail("followup js", "billing panel still gated on invoice checkbox")
        else:
            ok("Follow-up JS shows billing from customer select")

        print(f"\nSuffix {suffix} unused (unit checks only).")

    if failures:
        print(f"\n{len(failures)} failure(s)")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("\nAll billing customer workflow tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_tests())
