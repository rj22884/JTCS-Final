"""
Misc Activity → Create Invoice ledger + Money In/Out invoice category tests.

Run (isolated app DB session; cleans up created rows):
    cd erp
    .\\.venv\\Scripts\\python.exe scripts\\test_misc_invoice_ledger.py
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
    from sqlalchemy import func, select, text

    from app import create_app
    from app.extensions import db
    from app.models.bank_cash import OthersBankCashTransaction
    from app.models.gst_billing import GstInvoice
    from app.models.others import OthersIncomeExpenseDetail, OthersIncomeExpenseMaster, WorkMaster
    from app.models.transactions import JTCSDailyTransaction, WorkTypeMaster
    from app.repositories.transaction_repository import DailyTransactionRepository, MasterRepository
    from app.services.gst_invoice_service import GstInvoiceService
    from app.services.ledger_export_service import LedgerExportService
    from app.services.others_bank_cash_service import OthersBankCashService
    from app.services.payment_accounting_service import sql_unpaid_misc_exclusion_for_customer_ledger

    app = create_app()
    failures: list[str] = []
    suffix = uuid.uuid4().hex[:8]
    bill_no = f"MISC-TEST-{suffix}"
    inv_no = f"JTCS-MISC-{suffix}"
    created_by = f"test-misc-{suffix}"
    today = date.today()

    def ok(name: str) -> None:
        print(f"  OK  {name}")

    def fail(name: str, detail: str) -> None:
        failures.append(f"{name}: {detail}")
        print(f"  FAIL {name}: {detail}")

    with app.app_context():
        master = MasterRepository()
        daily_repo = DailyTransactionRepository()
        inv_svc = GstInvoiceService()
        obc = OthersBankCashService()
        ledger = LedgerExportService()

        cash = next(
            (
                a
                for a in master.list_active_bank_accounts()
                if (a.BankName or "").strip().lower() == "cash"
            ),
            None,
        )
        if cash is None:
            accounts = master.list_active_bank_accounts()
            cash = accounts[0] if accounts else None
        banks = master.list_active_bank_accounts()
        debit_bank = next(
            (a for a in banks if a.JtcsBankAccountID != getattr(cash, "JtcsBankAccountID", None)),
            cash,
        )
        customers = master.list_customers()
        if cash is None or debit_bank is None or not customers:
            fail("setup", "Need bank accounts and at least one customer")
            return 1
        cash_id = int(cash.JtcsBankAccountID)
        debit_bank_id = int(debit_bank.JtcsBankAccountID)
        alt_bank_id = next(
            (int(a.JtcsBankAccountID) for a in banks if int(a.JtcsBankAccountID) not in {cash_id, debit_bank_id}),
            debit_bank_id if debit_bank_id != cash_id else None,
        )
        customer = customers[0]
        customer_id = int(customer.CustomerID)
        customer_name = customer.CustomerName

        misc_work = db.session.scalars(
            select(WorkMaster).where(
                WorkMaster.ActiveStatus == True,  # noqa: E712
                WorkMaster.LedgerKind.in_(["Misc.", "Misc"]),
            )
        ).first()
        if misc_work is None:
            fail("setup", "No active WorkMaster with LedgerKind Misc.")
            return 1
        work_id = int(misc_work.WorkID)
        work_name = (misc_work.WorkName or "").strip()
        sub = db.session.scalars(
            select(WorkTypeMaster).where(
                WorkTypeMaster.ActiveStatus == True,  # noqa: E712
                WorkTypeMaster.WorkTypeName == work_name,
            )
        ).first()
        work_type_id = int(sub.WorkTypeID) if sub is not None else None
        sub_name = (sub.SubWorkType or "").strip() if sub is not None else ""

        purpose_row = db.session.execute(
            text(
                """
                SELECT TOP 1 PurposeName FROM dbo.PurposeMaster
                WHERE ISNULL(ActiveStatus, 1) = 1
                ORDER BY PurposeID
                """
            )
        ).first()
        purpose_name = purpose_row[0] if purpose_row else "Test Purpose"

        entry = None
        invoice_id = None
        daily_id = None
        obc_entry_ids: list[int] = []

        def movement_rows() -> list:
            sql = ledger._individual_client_movement_sql(
                customer_pred="e.CustomerID = :customer_id"
            )
            return list(
                db.session.execute(text(sql), {"customer_id": customer_id}).mappings().all()
            )

        def cleanup() -> None:
            for eid in list(obc_entry_ids):
                try:
                    obc.delete_entry(eid)
                except Exception:
                    db.session.rollback()
            if invoice_id:
                inv = db.session.get(GstInvoice, invoice_id)
                if inv is not None:
                    if getattr(inv, "DailyTransactionID", None):
                        d = db.session.get(JTCSDailyTransaction, inv.DailyTransactionID)
                        if d is not None:
                            daily_repo.delete(d)
                    db.session.delete(inv)
                    db.session.flush()
            if daily_id:
                d = db.session.get(JTCSDailyTransaction, daily_id)
                if d is not None:
                    daily_repo.delete(d)
            if entry is not None:
                for line in list(getattr(entry, "detail_lines", None) or []):
                    db.session.delete(line)
                db.session.delete(entry)
            db.session.flush()

        try:
            # --- exclusion helper present ---
            clause = sql_unpaid_misc_exclusion_for_customer_ledger()
            if "MiscEntryID" not in clause or "Sale / Service Invoice" not in clause:
                fail("exclusion SQL shape", clause[:200])
            else:
                ok("exclusion SQL helper includes MiscEntryID + Sale daily guard")

            # --- create Misc Activity row ---
            entry = OthersIncomeExpenseMaster(
                BillNo=bill_no,
                WorkDate=today,
                WorkID=work_id,
                Amount=Decimal("1000.00"),
                CustomerName=customer_name,
                CustomerID=customer_id,
                WorkDone=True,
                TallyBillGenerated=False,
                PaymentReceived=False,
                Remarks="test misc invoice ledger",
                CreatedBy=created_by,
                CreatedDate=datetime.utcnow(),
                IsActive=True,
            )
            db.session.add(entry)
            db.session.flush()
            db.session.add(
                OthersIncomeExpenseDetail(
                    EntryID=entry.EntryID,
                    LineSequence=1,
                    WorkID=work_id,
                    WorkTypeID=work_type_id,
                    Amount=Decimal("1000.00"),
                )
            )
            db.session.flush()

            before = [
                r
                for r in movement_rows()
                if (r.get("ReferenceNo") or "").strip().upper() == bill_no.upper()
                and Decimal(str(r.get("SaleAmount") or 0)) > 0
            ]
            if len(before) != 1 or (before[0].get("WorkType") or "") != "Misc.":
                fail("misc alone on ledger", f"rows={before}")
            else:
                ok("Misc Activity alone posts one Misc. debit on customer ledger")

            # --- Create Invoice (service) ---
            payload = {
                "invoice_date": today.isoformat(),
                "customer_id": customer_id,
                "customer_name": customer_name,
                "voucher_type": "SALE",
                "invoice_kind": "NON_GST",
                "bill_source": "MISCELLANEOUS",
                "misc_entry_id": entry.EntryID,
                "tally_bill_no": bill_no,
                "invoice_no": inv_no,
                "gst_inclusive": True,
                "lines": [
                    {
                        "particulars": f"Misc test {suffix}",
                        "qty": "1",
                        "rate": "1000",
                        "inclusive_gross": "1000",
                        "gst_rate_percent": "0",
                    }
                ],
            }
            created = inv_svc.create_record(payload, created_by=created_by, commit=False)
            invoice_id = int(created["invoice_id"])
            db.session.flush()

            after = [
                r
                for r in movement_rows()
                if bill_no.upper() in ((r.get("ReferenceNo") or "") + " " + (r.get("Description") or "")).upper()
                or inv_no.upper() in ((r.get("ReferenceNo") or "") + " " + (r.get("Description") or "")).upper()
            ]
            misc_debits = [
                r
                for r in after
                if (r.get("WorkType") or "") == "Misc."
                and Decimal(str(r.get("SaleAmount") or 0)) > 0
            ]
            sale_debits = [
                r
                for r in after
                if (r.get("SubWorkType") or "") == "Sale / Service Invoice"
                and Decimal(str(r.get("SaleAmount") or 0)) > 0
            ]
            if misc_debits:
                fail("no misc debit after invoice", f"misc={misc_debits}")
            elif len(sale_debits) != 1:
                fail("one sale debit after invoice", f"sale={sale_debits} all={after}")
            else:
                ok("Create Invoice -> one Sale/Service Invoice debit; Misc. debit suppressed")

            # --- idempotent Create Invoice ---
            again = inv_svc.create_record(payload, created_by=created_by, commit=False)
            db.session.flush()
            same_id = int(again["invoice_id"]) == invoice_id
            inv_count = db.session.scalar(
                select(func.count())
                .select_from(GstInvoice)
                .where(GstInvoice.MiscEntryID == entry.EntryID)
            )
            if not same_id or int(inv_count or 0) != 1:
                fail(
                    "idempotent create invoice",
                    f"first={invoice_id} second={again.get('invoice_id')} count={inv_count}",
                )
            else:
                ok("Retry Create Invoice does not create a second invoice")

            after_retry = [
                r
                for r in movement_rows()
                if (r.get("SubWorkType") or "") == "Sale / Service Invoice"
                and Decimal(str(r.get("SaleAmount") or 0)) > 0
                and (
                    inv_no.upper() in ((r.get("ReferenceNo") or "") + " " + (r.get("Description") or "")).upper()
                    or bill_no.upper() in ((r.get("ReferenceNo") or "") + " " + (r.get("Description") or "")).upper()
                )
            ]
            if len(after_retry) != 1:
                fail("idempotent ledger", f"sale rows={after_retry}")
            else:
                ok("Retry Create Invoice keeps a single customer-ledger sale debit")

            # --- Money In linked to invoice inherits category ---
            credit_key = f"coa-{customer_id}"
            # Prefer real customer COA key when available
            coa = db.session.execute(
                text(
                    """
                    SELECT TOP 1 AccountID FROM dbo.ChartOfAccountMaster
                    WHERE CustomerID = :cid AND ISNULL(IsActive, 1) = 1
                    ORDER BY AccountID
                    """
                ),
                {"cid": customer_id},
            ).first()
            if coa:
                credit_key = f"coa-{int(coa[0])}"
            else:
                # Fall back: credit a bank and still link via CustomerID + InvoiceMode
                credit_key = f"bank-{cash_id}"

            form = {
                "WorkDate": today.isoformat(),
                "Purpose": purpose_name,
                "CreditLedgerKey": credit_key,
                "DebitLedgerKey": f"bank-{debit_bank_id}",
                "Amount": "400.00",
                "Remarks": f"test misc payment {suffix}",
                "InvoiceMode": "selected",
                "CustomerID": str(customer_id),
                "InvoiceIDs": str(invoice_id),
                "WorkID": str(work_id),
                "WorkTypeID": str(work_type_id) if work_type_id else "",
            }
            try:
                saved = obc.save_entry(form, created_by=created_by)
                obc_entry_ids.append(saved.entry_id)
                db.session.flush()
                row = db.session.get(OthersBankCashTransaction, saved.entry_id)
                linked = obc.get_entry(saved.entry_id)
                alloc_ids = [a["invoice_id"] for a in linked.get("allocations") or []]
                if invoice_id not in alloc_ids and int(getattr(row, "InvoiceID", 0) or 0) != invoice_id:
                    fail("payment linked to invoice", f"alloc={alloc_ids} invoice_id={row.InvoiceID}")
                elif int(getattr(row, "WorkID", 0) or 0) != work_id:
                    fail("payment WorkID from invoice", f"got={row.WorkID} want={work_id}")
                elif work_type_id and int(getattr(row, "WorkTypeID", 0) or 0) != work_type_id:
                    fail("payment WorkTypeID from invoice", f"got={row.WorkTypeID} want={work_type_id}")
                else:
                    ok("Invoice-linked Money In inherits category/sub-work and links invoice")
            except ValueError as exc:
                # Customer credit ledger required for invoice mode when credit is bank-only
                if "customer" in str(exc).lower() and not coa:
                    fail("payment linked to invoice", f"no customer COA for test customer: {exc}")
                else:
                    fail("payment linked to invoice", str(exc))

            # --- backend rejects mismatched category ---
            if coa and work_type_id:
                bad = {
                    **form,
                    "Amount": "50.00",
                    "WorkID": str(work_id + 99999),
                    "VoucherNo": "",
                    "EntryID": "",
                }
                try:
                    obc.save_entry(bad, created_by=created_by)
                    fail("mismatch rejected", "save accepted wrong WorkID")
                except ValueError as exc:
                    if "category" in str(exc).lower() or "match" in str(exc).lower():
                        ok("Backend rejects WorkID mismatch vs invoice category")
                    else:
                        fail("mismatch rejected", str(exc))

            # --- clear invoice clears category ---
            if coa:
                out_id = cash_id
                in_id = debit_bank_id if debit_bank_id != cash_id else alt_bank_id
                if not in_id or in_id == out_id:
                    ok("non-invoice Money In skipped (need two bank accounts)")
                else:
                    clear_form = {
                        "WorkDate": today.isoformat(),
                        "Purpose": purpose_name,
                        "CreditLedgerKey": f"bank-{out_id}",
                        "DebitLedgerKey": f"bank-{in_id}",
                        "Amount": "25.00",
                        "Remarks": f"non-invoice obc {suffix}",
                        "InvoiceMode": "none",
                        "CustomerID": "",
                        "WorkID": str(work_id),
                        "WorkTypeID": str(work_type_id or ""),
                    }
                    saved2 = obc.save_entry(clear_form, created_by=created_by)
                    obc_entry_ids.append(saved2.entry_id)
                    db.session.flush()
                    row2 = db.session.get(OthersBankCashTransaction, saved2.entry_id)
                    if getattr(row2, "WorkID", None) is not None or getattr(row2, "InvoiceID", None):
                        fail(
                            "non-invoice clears category",
                            f"WorkID={row2.WorkID} InvoiceID={row2.InvoiceID}",
                        )
                    else:
                        ok("Non-invoice Money In clears invoice/category fields")

            # --- category resolver from invoice ---
            cat = obc._invoice_category(invoice_id)
            if cat.get("work_id") != work_id:
                fail("invoice category resolve", f"got={cat}")
            elif work_type_id and cat.get("work_type_id") != work_type_id:
                fail("invoice sub-work resolve", f"got={cat} want={work_type_id}/{sub_name}")
            else:
                ok("Invoice category/sub-work resolved from Misc Activity")

            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            fail("unexpected", repr(exc))
        finally:
            try:
                cleanup()
                db.session.commit()
            except Exception:
                db.session.rollback()

    if failures:
        print(f"\n{len(failures)} failure(s)")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("\nAll misc invoice ledger / Money In tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_tests())
