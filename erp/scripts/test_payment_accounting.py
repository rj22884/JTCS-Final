"""
Payment Received accounting tests (invoice debit vs payment credit).

Run:
    cd erp
    .\\.venv\\Scripts\\python.exe scripts\\test_payment_accounting.py
"""

from __future__ import annotations

import sys
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def run_tests() -> int:
    from app import create_app
    from app.extensions import db
    from app.models.transactions import JTCSDailyTransaction
    from app.repositories.transaction_repository import MasterRepository
    from app.services.followup_payment_service import FollowupPaymentService
    from app.services.ledger_export_service import LedgerExportService
    from app.services.payment_accounting_service import PaymentAccountingService

    app = create_app()
    failures: list[str] = []
    suffix = uuid.uuid4().hex[:8]
    bill_a = f"ITR-TEST-{suffix}-A"
    bill_b = f"ITR-TEST-{suffix}-B"
    bill_c = f"ITR-TEST-{suffix}-C"

    def ok(name: str) -> None:
        print(f"  OK  {name}")

    def fail(name: str, detail: str) -> None:
        failures.append(f"{name}: {detail}")
        print(f"  FAIL {name}: {detail}")

    with app.app_context():
        master = MasterRepository()
        cash = next(
            (a for a in master.list_active_bank_accounts() if (a.BankName or "").strip().lower() == "cash"),
            None,
        )
        if cash is None:
            accounts = master.list_active_bank_accounts()
            cash = accounts[0] if accounts else None
        if cash is None:
            fail("setup", "No bank/cash account in JtcsBankAccountMaster")
            return 1
        mode_id = master.resolve_payment_mode_for_bank_account(cash.JtcsBankAccountID)
        customers = master.list_customers()
        if not customers:
            fail("setup", "No customer in CustomerMaster")
            return 1
        customer = customers[0]
        customer_id = int(customer.CustomerID)
        customer_name = customer.CustomerName
        created_by = f"test-pay-{suffix}"
        svc = FollowupPaymentService("ITR")
        today = date.today()

        def lines(amount: Decimal) -> list[dict]:
            return [
                {
                    "bank_account_id": cash.JtcsBankAccountID,
                    "payment_mode_id": mode_id,
                    "amount": amount,
                    "payment_date": today,
                }
            ]

        def cleanup(*bills: str) -> None:
            for bill in bills:
                svc.remove_followup_accounting(bill)
            db.session.flush()

        try:
            # A. Invoice → Payment Received
            sale = svc.post_sale(
                bill_no=bill_a,
                work_date=today,
                amount=Decimal("1500.00"),
                customer_name=customer_name,
                customer_id=customer_id,
                remarks="test A",
                created_by=created_by,
            )
            pay = svc.post_payment(
                bill_no=bill_a,
                work_date=today,
                entry_amount=Decimal("1500.00"),
                payment_lines=lines(Decimal("1500.00")),
                customer_name=customer_name,
                customer_id=customer_id,
                remarks="test A",
                created_by=created_by,
            )
            db.session.flush()
            sale = db.session.get(JTCSDailyTransaction, sale.TransactionID)
            pay = db.session.get(JTCSDailyTransaction, pay.TransactionID)
            if sale is None or Decimal(str(sale.SaleAmount)) != Decimal("1500.00"):
                fail("A invoice debit", f"sale={None if sale is None else sale.SaleAmount}")
            elif pay is None or Decimal(str(pay.SaleAmount or 0)) != Decimal("0"):
                fail("A payment has no sale debit", f"pay.SaleAmount={None if pay is None else pay.SaleAmount}")
            elif sale.TransactionID == pay.TransactionID:
                fail("A separate txns", "sale and payment share TransactionID")
            else:
                ok("A Invoice then Payment Received (Dr 1500 / Cr 1500, no extra debit)")

            # B. Payment first → Invoice later
            adv = svc.post_payment(
                bill_no=bill_b,
                work_date=today,
                entry_amount=Decimal("1500.00"),
                payment_lines=lines(Decimal("1500.00")),
                customer_name=customer_name,
                customer_id=customer_id,
                remarks="test B",
                created_by=created_by,
            )
            db.session.flush()
            if Decimal(str(adv.SaleAmount or 0)) != Decimal("0"):
                fail("B advance no fake debit", f"SaleAmount={adv.SaleAmount}")
            else:
                sale_b = svc.post_sale(
                    bill_no=bill_b,
                    work_date=today,
                    amount=Decimal("1500.00"),
                    customer_name=customer_name,
                    customer_id=customer_id,
                    remarks="test B",
                    created_by=created_by,
                )
                db.session.flush()
                adv = db.session.get(JTCSDailyTransaction, adv.TransactionID)
                if sale_b is None or Decimal(str(sale_b.SaleAmount)) != Decimal("1500.00"):
                    fail("B later invoice", f"sale={None if sale_b is None else sale_b.SaleAmount}")
                elif Decimal(str(adv.SaleAmount or 0)) != Decimal("0"):
                    fail("B advance stayed credit-only", f"SaleAmount={adv.SaleAmount}")
                else:
                    ok("B Payment first then Invoice later")

            # C. Partial payment
            svc.post_sale(
                bill_no=bill_c,
                work_date=today,
                amount=Decimal("1500.00"),
                customer_name=customer_name,
                customer_id=customer_id,
                remarks="test C",
                created_by=created_by,
            )
            svc.post_payment(
                bill_no=bill_c,
                work_date=today,
                entry_amount=Decimal("1500.00"),
                payment_lines=lines(Decimal("500.00")),
                customer_name=customer_name,
                customer_id=customer_id,
                remarks="test C",
                created_by=created_by,
            )
            db.session.flush()
            remaining = PaymentAccountingService("ITR").remaining_invoice_amount(
                bill_c, invoice_amount=Decimal("1500.00")
            )
            if remaining != Decimal("1000.00"):
                fail("C partial remaining", f"remaining={remaining}")
            else:
                ok("C Partial payment leaves 1000 outstanding")

            # D. Multiple payments (replace lines with two modes / amounts totaling 1500)
            svc.post_payment(
                bill_no=bill_c,
                work_date=today,
                entry_amount=Decimal("1500.00"),
                payment_lines=lines(Decimal("500.00")) + lines(Decimal("1000.00")),
                customer_name=customer_name,
                customer_id=customer_id,
                remarks="test D",
                created_by=created_by,
            )
            db.session.flush()
            remaining = PaymentAccountingService("ITR").remaining_invoice_amount(
                bill_c, invoice_amount=Decimal("1500.00")
            )
            receipts = PaymentAccountingService("ITR").find_receipt_dailies(bill_c)
            if remaining != Decimal("0.00"):
                fail("D multiple payments remaining", f"remaining={remaining}")
            elif len(receipts) != 1:
                fail("D single receipt daily", f"count={len(receipts)}")
            else:
                ok("D Multiple payments against one invoice")

            # E. Duplicate payment attempt updates existing receipt (still one daily)
            first_id = receipts[0].TransactionID
            svc.post_payment(
                bill_no=bill_c,
                work_date=today,
                entry_amount=Decimal("1500.00"),
                payment_lines=lines(Decimal("1500.00")),
                customer_name=customer_name,
                customer_id=customer_id,
                remarks="test E",
                created_by=created_by,
                existing_daily=receipts[0],
            )
            db.session.flush()
            receipts2 = PaymentAccountingService("ITR").find_receipt_dailies(bill_c)
            if len(receipts2) != 1 or receipts2[0].TransactionID != first_id:
                fail("E duplicate updates existing", f"ids={[r.TransactionID for r in receipts2]}")
            else:
                ok("E Duplicate payment updates existing transaction")

            # F/G Edit then delete payment
            svc.post_payment(
                bill_no=bill_c,
                work_date=today,
                entry_amount=Decimal("1500.00"),
                payment_lines=lines(Decimal("700.00")),
                customer_name=customer_name,
                customer_id=customer_id,
                remarks="test F",
                created_by=created_by,
            )
            db.session.flush()
            remaining = PaymentAccountingService("ITR").remaining_invoice_amount(
                bill_c, invoice_amount=Decimal("1500.00")
            )
            if remaining != Decimal("800.00"):
                fail("F edit payment", f"remaining={remaining}")
            else:
                ok("F Edit payment updates accounting")
            svc.remove_receipts(bill_c)
            db.session.flush()
            remaining = PaymentAccountingService("ITR").remaining_invoice_amount(
                bill_c, invoice_amount=Decimal("1500.00")
            )
            sale_after = PaymentAccountingService("ITR").find_sale_daily(bill_c)
            if remaining != Decimal("1500.00"):
                fail("G delete payment remaining", f"remaining={remaining}")
            elif sale_after is None or Decimal(str(sale_after.SaleAmount)) != Decimal("1500.00"):
                fail("G delete keeps invoice debit", f"sale={sale_after}")
            else:
                ok("G Delete payment reverses receipt, keeps invoice debit")

            db.session.commit()

            # J. Customer ledger closing for scenario A
            ledger = LedgerExportService()._customer_ledger_data(
                customer_id, date_from=date(2000, 1, 1), date_to=today
            )
            a_lines = [ln for ln in ledger["lines"] if (ln.get("bill") or "").upper() == bill_a.upper()]
            debits = sum((ln.get("debit") or Decimal("0") for ln in a_lines), Decimal("0"))
            credits = sum((ln.get("credit") or Decimal("0") for ln in a_lines), Decimal("0"))
            both = [ln for ln in a_lines if (ln.get("debit") or 0) > 0 and (ln.get("credit") or 0) > 0]
            if both:
                fail("J no combined Dr+Cr line", f"lines={both}")
            elif debits != Decimal("1500.00") or credits != Decimal("1500.00"):
                fail("J ledger Dr/Cr", f"dr={debits} cr={credits} lines={a_lines}")
            else:
                ok("J Customer Ledger invoice Dr 1500 / payment Cr 1500")

        finally:
            cleanup(bill_a, bill_b, bill_c)
            db.session.commit()

    if failures:
        print(f"\n{len(failures)} failure(s)")
        return 1
    print("\nAll payment accounting tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_tests())
