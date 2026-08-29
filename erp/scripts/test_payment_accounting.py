"""
Payment Received accounting tests (invoice debit vs payment credit).

Run:
    cd erp
    .\\.venv\\Scripts\\python.exe scripts\\test_payment_accounting.py
"""

from __future__ import annotations

import sys
import uuid
from datetime import date, datetime
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
    from app.repositories.transaction_repository import DailyTransactionRepository, MasterRepository
    from app.services.followup_payment_service import FollowupPaymentService
    from app.services.ledger_export_service import LedgerExportService
    from app.services.payment_accounting_service import PaymentAccountingService

    app = create_app()
    failures: list[str] = []
    suffix = uuid.uuid4().hex[:8]
    bill_a = f"ITR-TEST-{suffix}-A"
    bill_b = f"ITR-TEST-{suffix}-B"
    bill_c = f"ITR-TEST-{suffix}-C"
    bill_h = f"ITR-TEST-{suffix}-H"
    bill_i = f"ITR-TEST-{suffix}-I"
    inv_a = f"JTCS-TEST-{suffix}-A"
    inv_b = f"JTCS-TEST-{suffix}-B"
    inv_c = f"JTCS-TEST-{suffix}-C"
    inv_h = f"JTCS-TEST-{suffix}-H"
    inv_i = f"JTCS-TEST-{suffix}-I"

    def ok(name: str) -> None:
        print(f"  OK  {name}")

    def fail(name: str, detail: str) -> None:
        failures.append(f"{name}: {detail}")
        print(f"  FAIL {name}: {detail}")

    with app.app_context():
        master = MasterRepository()
        daily_repo = DailyTransactionRepository()
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
        acct = PaymentAccountingService("ITR")
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

        def post_invoice(bill_no: str, invoice_no: str, amount: Decimal) -> JTCSDailyTransaction:
            return daily_repo.create(
                {
                    "TransactionDate": today,
                    "WorkType": "Accounting",
                    "SubWorkType": "Sale / Service Invoice",
                    "CustomerID": customer_id,
                    "CustomerName": customer_name,
                    "ReferenceNo": invoice_no,
                    "Description": f"Sale / Service Invoice — {invoice_no}",
                    "IncomeAmount": Decimal("0"),
                    "ExpenseAmount": Decimal("0"),
                    "SaleAmount": amount,
                    "PurchaseAmount": Decimal("0"),
                    "GSTAmount": Decimal("0"),
                    "TDSAmount": Decimal("0"),
                    "TotalAmount": amount,
                    "PaymentSplitCount": 1,
                    "Status": "Posted",
                    "CreatedBy": created_by,
                    "CreatedDate": datetime.utcnow(),
                    "Remarks": bill_no,
                }
            )

        def followup_sale_dailies(bill_no: str) -> list[JTCSDailyTransaction]:
            return [
                d
                for d in acct._module_dailies(bill_no)
                if acct._is_followup_sale_daily(d) and not acct._is_receipt_daily(d)
            ]

        def cleanup(*bills: str) -> None:
            for bill in bills:
                svc.remove_followup_accounting(bill)
                gst = PaymentAccountingService("ITR").find_gst_sale_daily(bill)
                if gst is not None and (gst.CreatedBy or "") == created_by:
                    daily_repo.delete(gst)
            db.session.flush()

        try:
            # A. Invoice → Payment Received (exact required ledger)
            sale = post_invoice(bill_a, inv_a, Decimal("1500.00"))
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
            extra = followup_sale_dailies(bill_a)
            if sale is None or Decimal(str(sale.SaleAmount)) != Decimal("1500.00"):
                fail("A invoice debit", f"sale={None if sale is None else sale.SaleAmount}")
            elif pay is None or Decimal(str(pay.SaleAmount or 0)) != Decimal("0"):
                fail("A payment has no sale debit", f"pay.SaleAmount={None if pay is None else pay.SaleAmount}")
            elif extra:
                fail("A no followup debit", f"ids={[d.TransactionID for d in extra]}")
            elif sale.TransactionID == pay.TransactionID:
                fail("A separate txns", "sale and payment share TransactionID")
            else:
                ok("A Invoice then Payment Received (Dr 1500 / Cr 1500, no follow-up debit)")

            # Follow-up post_sale must not create a second debit
            leftover = svc.post_sale(
                bill_no=bill_a,
                work_date=today,
                amount=Decimal("1500.00"),
                customer_name=customer_name,
                customer_id=customer_id,
                remarks="must not post",
                created_by=created_by,
            )
            db.session.flush()
            extra = followup_sale_dailies(bill_a)
            if extra:
                fail("A post_sale no-op", f"created {[d.SubWorkType for d in extra]}")
            elif leftover is not None and leftover.TransactionID != sale.TransactionID:
                fail("A post_sale returned other daily", f"id={leftover.TransactionID}")
            else:
                ok("A Follow-up post_sale does not create a receivable")

            # B. Payment first (no invoice) → Advance credit, no fake debit
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
            extra_b = followup_sale_dailies(bill_b)
            if Decimal(str(adv.SaleAmount or 0)) != Decimal("0"):
                fail("B advance no fake debit", f"SaleAmount={adv.SaleAmount}")
            elif extra_b:
                fail("B no followup debit", f"ids={[d.TransactionID for d in extra_b]}")
            elif not (adv.Description or "").lower().startswith("advance payment"):
                fail("B advance description", f"desc={adv.Description}")
            else:
                sale_b = post_invoice(bill_b, inv_b, Decimal("1500.00"))
                db.session.flush()
                PaymentAccountingService("ITR").reconcile_reference(bill_b)
                db.session.flush()
                adv = db.session.get(JTCSDailyTransaction, adv.TransactionID)
                extra_b2 = followup_sale_dailies(bill_b)
                if sale_b is None or Decimal(str(sale_b.SaleAmount)) != Decimal("1500.00"):
                    fail("B later invoice", f"sale={None if sale_b is None else sale_b.SaleAmount}")
                elif Decimal(str(adv.SaleAmount or 0)) != Decimal("0"):
                    fail("B advance stayed credit-only", f"SaleAmount={adv.SaleAmount}")
                elif extra_b2:
                    fail("B later invoice no followup debit", f"ids={[d.TransactionID for d in extra_b2]}")
                else:
                    ok("B Payment first is advance; later invoice does not add follow-up debit")

            # C. Partial payment against invoice
            post_invoice(bill_c, inv_c, Decimal("1500.00"))
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
            remaining = PaymentAccountingService("ITR").remaining_invoice_amount(bill_c)
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
            remaining = PaymentAccountingService("ITR").remaining_invoice_amount(bill_c)
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
            remaining = PaymentAccountingService("ITR").remaining_invoice_amount(bill_c)
            if remaining != Decimal("800.00"):
                fail("F edit payment", f"remaining={remaining}")
            else:
                ok("F Edit payment updates accounting")
            svc.remove_receipts(bill_c)
            db.session.flush()
            remaining = PaymentAccountingService("ITR").remaining_invoice_amount(bill_c)
            sale_after = PaymentAccountingService("ITR").find_sale_daily(bill_c)
            extra_c = followup_sale_dailies(bill_c)
            if remaining != Decimal("1500.00"):
                fail("G delete payment remaining", f"remaining={remaining}")
            elif sale_after is None or Decimal(str(sale_after.SaleAmount)) != Decimal("1500.00"):
                fail("G delete keeps invoice debit", f"sale={sale_after}")
            elif extra_c:
                fail("G no followup debit after receipt delete", f"ids={[d.TransactionID for d in extra_c]}")
            else:
                ok("G Delete payment reverses receipt, keeps invoice debit")

            # H. Recon removes leftover ITR Followup sale when invoice already exists
            post_invoice(bill_h, inv_h, Decimal("1500.00"))
            leftover_sale = daily_repo.create(
                {
                    "TransactionDate": today,
                    "WorkType": "ITR",
                    "SubWorkType": "ITR Followup",
                    "CustomerID": customer_id,
                    "CustomerName": customer_name,
                    "ReferenceNo": bill_h,
                    "Description": f"ITR Followup — {bill_h}",
                    "IncomeAmount": Decimal("0"),
                    "ExpenseAmount": Decimal("0"),
                    "SaleAmount": Decimal("1500.00"),
                    "PurchaseAmount": Decimal("0"),
                    "GSTAmount": Decimal("0"),
                    "TDSAmount": Decimal("0"),
                    "TotalAmount": Decimal("1500.00"),
                    "PaymentSplitCount": 1,
                    "Status": "Posted",
                    "CreatedBy": created_by,
                    "CreatedDate": datetime.utcnow(),
                    "Remarks": bill_h,
                }
            )
            leftover_id = leftover_sale.TransactionID
            db.session.flush()
            PaymentAccountingService("ITR").reconcile_reference(bill_h)
            db.session.flush()
            gone = db.session.get(JTCSDailyTransaction, leftover_id)
            extra_h = followup_sale_dailies(bill_h)
            gst_h = PaymentAccountingService("ITR").find_gst_sale_daily(bill_h)
            if gone is not None and Decimal(str(gone.SaleAmount or 0)) != Decimal("0"):
                fail("H recon removed followup debit", f"still SaleAmount={gone.SaleAmount}")
            elif extra_h:
                fail("H no followup sale left", f"ids={[d.TransactionID for d in extra_h]}")
            elif gst_h is None or Decimal(str(gst_h.SaleAmount)) != Decimal("1500.00"):
                fail("H invoice debit kept", f"gst={gst_h}")
            else:
                ok("H Recon deletes leftover Follow-up debit when invoice exists")

            # I. Payment Received must not overwrite the GST invoice daily
            gst_i = post_invoice(bill_i, inv_i, Decimal("2000.00"))
            gst_id = gst_i.TransactionID
            pay_i = svc.post_payment(
                bill_no=bill_i,
                work_date=today,
                entry_amount=Decimal("2000.00"),
                payment_lines=lines(Decimal("2000.00")),
                customer_name=customer_name,
                customer_id=customer_id,
                remarks="test I",
                created_by=created_by,
                existing_daily=gst_i,
            )
            db.session.flush()
            gst_i = db.session.get(JTCSDailyTransaction, gst_id)
            found_i = acct.find_receipt_daily(bill_i)
            dates_i = svc.payment_dates_by_bills({bill_i})
            if gst_i is None or Decimal(str(gst_i.SaleAmount)) != Decimal("2000.00"):
                fail("I gst debit kept", f"sale={None if gst_i is None else gst_i.SaleAmount}")
            elif (gst_i.SubWorkType or "") != "Sale / Service Invoice":
                fail("I gst subwork kept", f"sub={gst_i.SubWorkType}")
            elif pay_i is None or pay_i.TransactionID == gst_id:
                fail("I separate receipt", f"pay={None if pay_i is None else pay_i.TransactionID}")
            elif found_i is None or found_i.TransactionID != pay_i.TransactionID:
                fail("I find_receipt_daily", f"found={None if found_i is None else found_i.TransactionID}")
            elif not dates_i.get(bill_i.upper()):
                fail("I payment dates", f"dates={dates_i}")
            elif (pay_i.WorkType or "") != "ITR":
                fail("I receipt work type", f"work={pay_i.WorkType}")
            else:
                ok("I Payment Received does not overwrite GST invoice daily")
            cleanup(bill_i)

            db.session.commit()

            # J. Customer ledger closing for scenario A
            ledger = LedgerExportService()._customer_ledger_data(
                customer_id, date_from=date(2000, 1, 1), date_to=today
            )
            wanted = {bill_a.upper(), inv_a.upper()}
            a_lines = [
                ln
                for ln in ledger["lines"]
                if (ln.get("bill") or "").upper() in wanted
                or bill_a.upper() in (ln.get("description") or "").upper()
                or inv_a.upper() in (ln.get("description") or "").upper()
            ]
            debits = sum((ln.get("debit") or Decimal("0") for ln in a_lines), Decimal("0"))
            credits = sum((ln.get("credit") or Decimal("0") for ln in a_lines), Decimal("0"))
            followup_debit = [
                ln
                for ln in a_lines
                if "followup" in (ln.get("description") or "").lower()
                and (ln.get("debit") or 0) > 0
                and "receipt" not in (ln.get("work") or "").lower()
            ]
            both = [ln for ln in a_lines if (ln.get("debit") or 0) > 0 and (ln.get("credit") or 0) > 0]
            if both:
                fail("J no combined Dr+Cr line", f"lines={both}")
            elif followup_debit:
                fail("J no followup debit in ledger", f"lines={followup_debit}")
            elif debits != Decimal("1500.00") or credits != Decimal("1500.00"):
                fail("J ledger Dr/Cr", f"dr={debits} cr={credits} lines={a_lines}")
            else:
                ok("J Customer Ledger invoice Dr 1500 / payment Cr 1500 / closing 0")

        finally:
            cleanup(bill_a, bill_b, bill_c, bill_h, bill_i)
            db.session.commit()

    if failures:
        print(f"\n{len(failures)} failure(s)")
        return 1
    print("\nAll payment accounting tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_tests())
