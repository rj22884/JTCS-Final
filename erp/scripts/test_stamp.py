"""
JTCS ERP Stamp Activity test suite.

Run:
    cd erp
    .\.venv\Scripts\Activate.ps1
    python scripts/test_stamp.py
"""
from __future__ import annotations

import sys
import uuid
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app
from app.exceptions.stamp_exceptions import StampDuplicateError
from app.repositories.stamp_repository import StampRepository
from app.repositories.transaction_repository import MasterRepository
from app.services.stamp_ocr_service import StampOcrService
from app.services.stamp_service import StampService


SAMPLE_CERT_TEXT = """
Government of Uttarakhand
e-Stamp Certificate
Certificate No.
:
IN-UK80596276301039Y
Certificate Issued Date
:
05-Jul-2026 11:55 AM
Account Reference
:
ACC123
Purchased by
:
test
Description of Document
:
Sale Deed
First Party
:
test
Second Party
:
test
Stamp Duty Paid By
:
test
Stamp Duty Amount(Rs.)
:
1 (One only)
"""


def run_tests() -> int:
    app = create_app()
    failures: list[str] = []
    suffix = uuid.uuid4().hex[:8]
    cert_number = f"TEST-STAMP-{suffix}"
    zero_cert = f"TEST-ZERO-{suffix}"

    def ok(name: str) -> None:
        print(f"  OK  {name}")

    def fail(name: str, detail: str) -> None:
        failures.append(f"{name}: {detail}")
        print(f"  FAIL {name}: {detail}")

    with app.app_context():
        master = MasterRepository()
        stamp_modes = master.list_stamp_bank_payment_modes()
        cash_mode = next((m for m in stamp_modes if m["display_account_number"] == "Cash"), None)
        if cash_mode is None:
            fail("Payment mode setup", "Cash bank account not found in JtcsBankAccountMaster")
            return 1
        if len(stamp_modes) < 1:
            fail("Payment mode setup", "no active bank accounts in JtcsBankAccountMaster")
        elif not all(m.get("bank_account_id") for m in stamp_modes):
            fail("Payment mode setup", "bank_account_id missing from payment options")
        else:
            ok(f"Payment modes loaded from JtcsBankAccountMaster ({len(stamp_modes)} accounts)")

        print("\n=== OCR parsing (Uttarakhand label mapping) ===")
        ocr = StampOcrService()
        try:
            fields = ocr.parse_certificate_text(SAMPLE_CERT_TEXT)
            expectations = {
                "CertificateNumber": "IN-UK80596276301039Y",
                "CertificateIssuedDate": "2026-07-05",
                "PurchasedBy": "test",
                "FirstPartyName": "test",
                "SecondPartyName": "test",
                "StampDutyPaidBy": "test",
                "StampDutyAmount": "1.00",
            }
            for key, expected in expectations.items():
                actual = fields.get(key)
                if actual == expected:
                    ok(f"{key} = {actual}")
                else:
                    fail(f"{key}", f"expected {expected!r}, got {actual!r}")

            amount_cases = [
                ("Stamp Duty Amount(Rs.) : 1 (One only)", "1.00"),
                ("1 (One only)", "1.00"),
                (": 1 (One only)", "1.00"),
                ("1 (One only) Article 4 Affidavit (Statute)", "1.00"),
                ("(One only) Article 4 Affidavit", "1.00"),
                ("One only", "1.00"),
                ("(Rs: ) (One only)", "1.00"),
                ("500 (Five hundred only)", "500.00"),
            ]
            row_text = """Stamp Duty Paid By
test
Stamp Duty Amount(Rs.)
(One only)"""
            row_amount = ocr._extract_stamp_duty_row_amount(ocr._normalize_ocr_text(row_text))
            if row_amount == "1.00":
                ok("Stamp Duty row OCR split -> 1.00")
            else:
                fail("Stamp Duty row OCR split", f"expected '1.00', got {row_amount!r}")
            row_text2 = "Stamp Duty Amount(Rs.) : 1 (One only)"
            row_amount2 = ocr._extract_stamp_duty_row_amount(row_text2)
            if row_amount2 == "1.00":
                ok("Stamp Duty row colon rule -> 1.00")
            else:
                fail("Stamp Duty row colon rule", f"expected '1.00', got {row_amount2!r}")
            for raw, expected in amount_cases:
                actual = ocr._parse_stamp_duty_amount(raw)
                if actual == expected:
                    ok(f"StampDutyAmount parse {raw!r} = {actual}")
                else:
                    fail(f"StampDutyAmount parse {raw!r}", f"expected {expected!r}, got {actual!r}")

            garbled = """
            Government of Uttarakhand
            Certiticate Number
            IN UK80596276301039Y
            Certificate Issued Date : 05-Jul-2026 11.55 AM
            Purchased by : test
            First Party : RAM SINGH
            Second Party : SHYAM SINGH
            Stamp Duty Paid By : RAM SINGH
            Stamp Duty Amount(Rs.) : 1 (One only)
            """
            garbled_fields = ocr.parse_certificate_text(garbled)
            if garbled_fields.get("CertificateNumber") == "IN-UK80596276301039Y":
                ok("Garbled OCR still finds IN-UK certificate number")
            else:
                fail(
                    "Garbled certificate number",
                    f"got {garbled_fields.get('CertificateNumber')!r}",
                )
            unlabeled = "IN-UK80596276301039Y First Party test Stamp Duty Amount(Rs.) : 500 (Five hundred only)"
            unlabeled_fields = ocr.parse_certificate_text(unlabeled)
            if unlabeled_fields.get("CertificateNumber") == "IN-UK80596276301039Y":
                ok("Unlabeled IN-UK certificate number fallback")
            else:
                fail(
                    "Unlabeled certificate number",
                    f"got {unlabeled_fields.get('CertificateNumber')!r}",
                )
            vps_tesseract = """
            Government of Uttarakhand
            Certificate No. IN-UK93689528000869Y
            Certifcate Issued Date
            28-Aug-2026 05:47 PM
            Account Reference NONACC (SV)/ uk1423304/ HALDWANI/ UK-NT
            Unique Doc. Reference SUBIN-UKUK142330491727791236986Y
            Purchased by PUSHPA JOSHI
            Description of Document Article 5 Agreement or Memorandum of an agreement
            Property Description NA
            Consideration Price (Rs.) 0 (Zero)
            Fst Party^ PUSHPA JOSHI
            Second Party EE TD PWD BHOWALI
            'stamp Duty Pai By PUSHPA JOSHI
            Stamp Duty Amount(Rs.) 100 (One Hundred only)
            """
            vps_fields = ocr.parse_certificate_text(vps_tesseract)
            vps_expectations = {
                "CertificateNumber": "IN-UK93689528000869Y",
                "CertificateIssuedDate": "2026-08-28",
                "PurchasedBy": "PUSHPA JOSHI",
                "FirstPartyName": "PUSHPA JOSHI",
                "SecondPartyName": "EE TD PWD BHOWALI",
                "StampDutyPaidBy": "PUSHPA JOSHI",
                "StampDutyAmount": "100.00",
                "UniqueDocumentReference": "SUBIN-UKUK142330491727791236986Y",
            }
            vps_ok = True
            for key, expected in vps_expectations.items():
                actual = vps_fields.get(key)
                if actual != expected:
                    fail(f"VPS Tesseract {key}", f"expected {expected!r}, got {actual!r}")
                    vps_ok = False
            if vps_ok:
                ok("VPS-like Tesseract certificate extracts all required fields")

            colon_cert = """
            Government of Uttarakhand
            Certificate No. : IN-UK93722611761431Y
            Certificate Issued Date : 29-Aug-2026 11:13 AM
            Account Reference : NONACC (SV)/ uk1423304/ HALDWANI/ UK-NT
            Unique Doc. Reference : SUBIN-UKUK142330491797720836181Y
            Purchased by : LAL CHAND KUMAWAT
            Description of Document : Article 35 Lease
            Property Description : NA
            Consideration Price (Rs.) : 0 (Zero)
            First Party : PREM BALLABH SHARMA SO NARAYAN DATT SHARMA
            Second Party : LAL CHAND KUMAWAT
            Stamp Duty Paid By : LAL CHAND KUMAWAT
            Stamp Duty Amount(Rs.) : 100 (One Hundred only)
            """
            colon_fields = ocr.parse_certificate_text(colon_cert)
            colon_expectations = {
                "CertificateNumber": "IN-UK93722611761431Y",
                "PurchasedBy": "LAL CHAND KUMAWAT",
                "StampDutyPaidBy": "LAL CHAND KUMAWAT",
                "FirstPartyName": "PREM BALLABH SHARMA SO NARAYAN DATT SHARMA",
                "SecondPartyName": "LAL CHAND KUMAWAT",
                "DescriptionOfDocument": "Article 35 Lease",
                "StampDutyAmount": "100.00",
            }
            colon_ok = True
            for key, expected in colon_expectations.items():
                actual = colon_fields.get(key)
                if actual != expected:
                    fail(f"Colon-line {key}", f"expected {expected!r}, got {actual!r}")
                    colon_ok = False
            if colon_ok:
                ok("Colon-line certificate maps values after ':'")

            gt_cert = """
            Purchased by > LAL CHAND KUMAWAT
            Stamp Duty Paid By > LAL CHAND KUMAWAT
            First Party > PREM BALLABH SHARMA
            Second Party > LAL CHAND KUMAWAT
            Stamp Duty Amount(Rs.) : 100 (One Hundred only)
            Certificate No. : IN-UK93722611761431Y
            """
            gt_fields = ocr.parse_certificate_text(gt_cert)
            if gt_fields.get("PurchasedBy") == "LAL CHAND KUMAWAT" and gt_fields.get("StampDutyPaidBy") == "LAL CHAND KUMAWAT":
                ok("OCR '>' prefix is stripped from party names")
            else:
                fail(
                    "OCR '>' prefix",
                    f"PurchasedBy={gt_fields.get('PurchasedBy')!r} PaidBy={gt_fields.get('StampDutyPaidBy')!r}",
                )
            hundred = ocr._word_amount("One Hundred")
            if hundred == "100.00":
                ok("Word amount One Hundred -> 100.00")
            else:
                fail("Word amount One Hundred", f"got {hundred!r}")
            try:
                partial = ocr.parse_certificate_text("First Party : RAM SINGH\nStamp Duty Amount(Rs.) : 1 (One only)")
                if partial.get("FirstPartyName") == "RAM SINGH":
                    ok("Missing certificate number still returns partial fields")
                else:
                    fail("Partial OCR fields", f"got {partial!r}")
            except Exception as exc:
                fail("Partial OCR should not raise", str(exc))
        except Exception as exc:
            fail("OCR parsing", str(exc))

        print("\n=== Save with bank (SaleAmount > StampDutyAmount) ===")
        stamp_service = StampService()
        form = {
            "EntryMode": "manual",
            "CertificateNumber": cert_number,
            "CertificateIssuedDate": date.today().isoformat(),
            "StampDutyPaidBy": "test",
            "StampDutyAmount": "5000",
            "TransactionDate": date.today().isoformat(),
            "SaleAmount": "5001",
            "BankAccountID": str(cash_mode["bank_account_id"]),
            "ReferenceNo": cert_number,
            "Narration": "Stamp Sale",
        }

        try:
            result = stamp_service.save_stamp_activity(form, created_by="stamp.test")
            if result.bank_transaction_id:
                ok(f"Saved with bank txn #{result.bank_transaction_id}")
            else:
                fail("Bank transaction", "missing for SaleAmount > 0")
        except Exception as exc:
            fail("Save stamp activity", str(exc))
            result = None

        if result:
            try:
                stamp_service.save_stamp_activity(form, created_by="stamp.test")
                fail("Duplicate blocked", "save succeeded unexpectedly")
            except StampDuplicateError:
                ok("Duplicate raises StampDuplicateError")
            except Exception as exc:
                fail("Duplicate blocked", str(exc))

        print("\n=== Mandatory field validation ===")
        try:
            stamp_service.validate_form({"CertificateNumber": "ONLY-CERT"})
            fail("Mandatory validation", "incomplete form accepted")
        except ValueError as exc:
            if "Certificate Date" in str(exc):
                ok("Incomplete form rejected — " + str(exc))
            else:
                fail("Mandatory validation", str(exc))

        print("\n=== Save rejected when SaleAmount <= StampDutyAmount ===")
        zero_form = {
            "EntryMode": "manual",
            "CertificateNumber": zero_cert,
            "CertificateIssuedDate": date.today().isoformat(),
            "StampDutyPaidBy": "test",
            "StampDutyAmount": "1",
            "TransactionDate": date.today().isoformat(),
            "SaleAmount": "0",
            "ReferenceNo": zero_cert,
        }
        try:
            stamp_service.save_stamp_activity(zero_form, created_by="stamp.test")
            fail("Zero sale save", "save succeeded unexpectedly")
        except ValueError as exc:
            if "Sale Amount" in str(exc):
                ok("Zero Sale Amount rejected — " + str(exc))
            else:
                fail("Zero sale save", str(exc))

        print("\n=== Duplicate lookup ===")
        try:
            info = stamp_service.check_certificate(cert_number)
            if info.get("exists") and info.get("transaction_id"):
                ok("Duplicate lookup returns transaction details")
            else:
                fail("Duplicate lookup", str(info))
        except Exception as exc:
            fail("Duplicate lookup", str(exc))

        print("\n=== Search and delete ===")
        try:
            rows = stamp_service.search_records(cert_number[:8])
            if not any(r["certificate_number"] == cert_number for r in rows):
                fail("Search by certificate", f"expected {cert_number!r} in results")
            else:
                ok(f"Search by certificate prefix -> {len(rows)} row(s)")

            record = stamp_service.get_record(result.stamp_id)
            if record.get("CertificateNumber") != cert_number:
                fail("Get record", f"expected {cert_number!r}, got {record.get('CertificateNumber')!r}")
            else:
                ok("Get record by stamp_id")

            delete_cert = f"TEST-DEL-{suffix}"
            del_result = stamp_service.save_stamp_activity(
                {
                    "EntryMode": "manual",
                    "CertificateNumber": delete_cert,
                    "CertificateIssuedDate": date.today().isoformat(),
                    "StampDutyPaidBy": "test",
                    "StampDutyAmount": "100",
                    "SaleAmount": "101",
                    "BankAccountID": str(cash_mode["bank_account_id"]),
                },
                created_by="stamp.test",
            )
            stamp_service.delete_stamp(del_result.stamp_id, deleted_by="stamp.test")
            deleted_rows = stamp_service.search_records(delete_cert)
            if deleted_rows:
                fail("Delete stamp", "record still returned by search")
            else:
                ok("Delete stamp removes record from search")
        except Exception as exc:
            fail("Search/delete", str(exc))

        print("\n=== Multiple payment modes ===")
        try:
            from werkzeug.datastructures import ImmutableMultiDict

            split_cert = f"TEST-SPLIT-{suffix}"
            second_mode = stamp_modes[1] if len(stamp_modes) > 1 else cash_mode
            split_form = ImmutableMultiDict(
                [
                    ("EntryMode", "manual"),
                    ("CertificateNumber", split_cert),
                    ("CertificateIssuedDate", date.today().isoformat()),
                    ("StampDutyPaidBy", "test"),
                    ("StampDutyAmount", "100"),
                    ("SaleAmount", "250"),
                    ("PaymentBankAccountID[]", str(cash_mode["bank_account_id"])),
                    ("PaymentAmount[]", "100"),
                    ("PaymentBankAccountID[]", str(second_mode["bank_account_id"])),
                    ("PaymentAmount[]", "150"),
                ]
            )
            split_result = stamp_service.save_stamp_activity(split_form, created_by="stamp.test")
            if len(split_result.bank_transaction_ids) != 2:
                fail("Multiple payment save", f"expected 2 bank rows, got {split_result.bank_transaction_ids!r}")
            else:
                ok("Multiple payment modes create two bank transactions")
            record = stamp_service.get_record(split_result.stamp_id)
            if len(record.get("payments") or []) != 2:
                fail("Multiple payment load", f"expected 2 payment lines, got {record.get('payments')!r}")
            else:
                ok("Multiple payment lines loaded on get_record")

            update_form = ImmutableMultiDict(
                [
                    ("StampID", str(split_result.stamp_id)),
                    ("EntryMode", "manual"),
                    ("CertificateNumber", split_cert),
                    ("CertificateIssuedDate", date.today().isoformat()),
                    ("StampDutyPaidBy", "test"),
                    ("StampDutyAmount", "100"),
                    ("SaleAmount", "300"),
                    ("PaymentBankAccountID[]", str(cash_mode["bank_account_id"])),
                    ("PaymentAmount[]", "120"),
                    ("PaymentBankAccountID[]", str(second_mode["bank_account_id"])),
                    ("PaymentAmount[]", "180"),
                ]
            )
            update_result = stamp_service.save_stamp_activity(update_form, created_by="stamp.test")
            if update_result.stamp_id != split_result.stamp_id:
                fail("Update stamp", f"expected same stamp_id, got {update_result.stamp_id!r}")
            elif len(update_result.bank_transaction_ids) != 2:
                fail("Update payments", f"expected 2 bank rows after update, got {update_result.bank_transaction_ids!r}")
            else:
                ok("Update stamp keeps same ID with two payment lines")
            updated_record = stamp_service.get_record(split_result.stamp_id)
            if len(updated_record.get("payments") or []) != 2:
                fail("Update payment load", f"expected 2 lines after edit, got {updated_record.get('payments')!r}")
            elif float(updated_record.get("SaleAmount") or 0) != 300.0:
                fail("Update sale amount", f"expected 300, got {updated_record.get('SaleAmount')!r}")
            else:
                ok("Edit reloads all payment lines and updated sale amount")

            update_form2 = ImmutableMultiDict(
                [
                    ("StampID", str(split_result.stamp_id)),
                    ("EntryMode", "manual"),
                    ("CertificateNumber", split_cert),
                    ("CertificateIssuedDate", date.today().isoformat()),
                    ("StampDutyPaidBy", "test"),
                    ("StampDutyAmount", "100"),
                    ("SaleAmount", "300"),
                    ("PaymentBankAccountID[]", str(cash_mode["bank_account_id"])),
                    ("PaymentAmount[]", "120"),
                    ("PaymentBankAccountID[]", str(second_mode["bank_account_id"])),
                    ("PaymentAmount[]", "180"),
                ]
            )
            resave = stamp_service.save_stamp_activity(update_form2, created_by="stamp.test")
            if len(resave.bank_transaction_ids) != 2:
                fail("Double save payments", f"expected 2 bank rows on 2nd save, got {resave.bank_transaction_ids!r}")
            else:
                ok("Second save keeps two payment lines")
            resave_record = stamp_service.get_record(split_result.stamp_id)
            if len(resave_record.get("payments") or []) != 2:
                fail("Double edit load", f"expected 2 lines after 2nd save/edit, got {resave_record.get('payments')!r}")
            else:
                ok("Second edit reloads all payment lines")

            third_mode = stamp_modes[2] if len(stamp_modes) > 2 else second_mode
            triple_form = ImmutableMultiDict(
                [
                    ("StampID", str(split_result.stamp_id)),
                    ("EntryMode", "manual"),
                    ("CertificateNumber", split_cert),
                    ("CertificateIssuedDate", date.today().isoformat()),
                    ("StampDutyPaidBy", "test"),
                    ("StampDutyAmount", "100"),
                    ("SaleAmount", "320"),
                    ("PaymentBankAccountID[]", str(cash_mode["bank_account_id"])),
                    ("PaymentAmount[]", "120"),
                    ("PaymentBankAccountID[]", str(second_mode["bank_account_id"])),
                    ("PaymentAmount[]", "100"),
                    ("PaymentBankAccountID[]", str(third_mode["bank_account_id"])),
                    ("PaymentAmount[]", "100"),
                ]
            )
            stamp_service.save_stamp_activity(triple_form, created_by="stamp.test")
            triple_record = stamp_service.get_record(split_result.stamp_id)
            if len(triple_record.get("payments") or []) != 3:
                fail("Add payment line", f"expected 3 lines, got {triple_record.get('payments')!r}")
            else:
                ok("Add third payment line persists on reload")

            dual_form = ImmutableMultiDict(
                [
                    ("StampID", str(split_result.stamp_id)),
                    ("EntryMode", "manual"),
                    ("CertificateNumber", split_cert),
                    ("CertificateIssuedDate", date.today().isoformat()),
                    ("StampDutyPaidBy", "test"),
                    ("StampDutyAmount", "100"),
                    ("SaleAmount", "220"),
                    ("PaymentBankAccountID[]", str(cash_mode["bank_account_id"])),
                    ("PaymentAmount[]", "120"),
                    ("PaymentBankAccountID[]", str(second_mode["bank_account_id"])),
                    ("PaymentAmount[]", "100"),
                ]
            )
            stamp_service.save_stamp_activity(dual_form, created_by="stamp.test")
            dual_record = stamp_service.get_record(split_result.stamp_id)
            if len(dual_record.get("payments") or []) != 2:
                fail("Remove payment line", f"expected 2 lines after delete, got {dual_record.get('payments')!r}")
            else:
                ok("Removed payment line persists on reload")

            edit_same_cert = ImmutableMultiDict(
                [
                    ("StampID", str(split_result.stamp_id)),
                    ("EditStampID", str(split_result.stamp_id)),
                    ("EntryMode", "manual"),
                    ("CertificateNumber", split_cert),
                    ("CertificateIssuedDate", date.today().isoformat()),
                    ("StampDutyPaidBy", "test"),
                    ("StampDutyAmount", "100"),
                    ("SaleAmount", "220"),
                    ("PaymentBankAccountID[]", str(cash_mode["bank_account_id"])),
                    ("PaymentAmount[]", "120"),
                    ("PaymentBankAccountID[]", str(second_mode["bank_account_id"])),
                    ("PaymentAmount[]", "100"),
                ]
            )
            same_cert_result = stamp_service.save_stamp_activity(edit_same_cert, created_by="stamp.test")
            if same_cert_result.stamp_id != split_result.stamp_id:
                fail("Edit same certificate", f"expected stamp {split_result.stamp_id}, got {same_cert_result.stamp_id!r}")
            else:
                ok("Edit save accepts same certificate when StampID is posted")
        except Exception as exc:
            fail("Multiple payment modes", str(exc))

        print("\n=== Stamp does not write CustomerMaster ===")
        try:
            master_repo = MasterRepository()
            customer_cert = f"TEST-CUST-{suffix}"
            customer_mobile = "9876543210"
            customer_name = f"Stamp Customer {suffix}"
            before = {c.CustomerID for c in master_repo.list_customers_by_mobile(customer_mobile)}
            mobile_save = stamp_service.save_stamp_activity(
                {
                    "EntryMode": "manual",
                    "CertificateNumber": customer_cert,
                    "CertificateIssuedDate": date.today().isoformat(),
                    "StampDutyPaidBy": customer_name,
                    "MobileNumber": customer_mobile,
                    "StampDutyAmount": "10",
                    "SaleAmount": "20",
                    "BankAccountID": str(cash_mode["bank_account_id"]),
                },
                created_by="stamp.test",
            )
            after = master_repo.list_customers_by_mobile(customer_mobile)
            created = [c for c in after if c.CustomerName == customer_name and c.CustomerID not in before]
            if created:
                fail("CustomerMaster isolation", f"stamp saved {customer_name!r} into CustomerMaster")
            else:
                ok("Stamp party name is not written to CustomerMaster")
            saved = stamp_service.get_record(mobile_save.stamp_id)
            if saved.get("MobileNumber") == customer_mobile:
                ok("Stamp save persists MobileNumber on StampMaster")
            else:
                fail("Stamp mobile persist", f"expected {customer_mobile!r}, got {saved.get('MobileNumber')!r}")
            from app.repositories.stamp_repository import StampGridFilters

            grid = stamp_service.grid_data(
                StampGridFilters(certificate=customer_cert, mobile=customer_mobile)
            )
            grid_row = next(
                (r for r in grid.get("rows") or [] if r.get("certificate_number") == customer_cert),
                None,
            )
            if grid_row and grid_row.get("mobile_number") == customer_mobile:
                ok("Stamp grid shows saved mobile without CustomerMaster")
            else:
                fail("Stamp grid mobile", f"got {grid_row!r}")
        except Exception as exc:
            fail("CustomerMaster isolation", str(exc))

        print("\n=== Report handlers ===")
        from app.services.report_service import ReportFilters, ReportService

        report_service = ReportService()
        filters = ReportFilters(start_date=date.today(), end_date=date.today())
        for key in (
            "stamp-register",
            "stamp-daily-sale",
            "stamp-collection",
            "stamp-customer-wise",
            "stamp-certificate-wise",
            "stamp-date-wise",
            "stamp-payment-mode",
        ):
            try:
                payload = report_service.run(key, filters)
                ok(f"Report '{key}' ({len(payload.get('rows', []))} rows)")
            except Exception as exc:
                fail(f"Report '{key}'", str(exc))

    print("\n=== Summary ===")
    if failures:
        print(f"FAILED: {len(failures)} test(s)")
        for item in failures:
            print(f"  - {item}")
        return 1

    print("All stamp tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_tests())
