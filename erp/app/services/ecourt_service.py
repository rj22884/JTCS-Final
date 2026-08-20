from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.extensions import db
from app.models.transactions import JTCSDailyTransaction
from app.utils.shcil_bank_accounts import find_ecourt_purchase_bank
from app.repositories.ecourt_repository import ECourtRepository
from app.repositories.transaction_repository import (
    BankTransactionRepository,
    DailyTransactionPaymentRepository,
    DailyTransactionRepository,
    MasterRepository,
)
from app.services.ecourt_pdf_service import ECourtPdfService


class ECourtService:
    SOLD = "Sold"
    NOT_SOLD = "Not Sold"
    PARTIALLY_SOLD = "Partially Sold"
    MAX_IMPORT_AMOUNT = Decimal("500")
    MIN_IMPORT_AMOUNT = Decimal("1")
    SMALL_AMOUNT_MAX = Decimal("10")
    HIGH_AMOUNT_MIN = Decimal("11")
    BLOCK_SIZE = 20
    WORK_TYPE = "SHCIL"
    SUB_WORK_TYPE = "e-Court Activity"

    def __init__(
        self,
        repository: ECourtRepository | None = None,
        daily_repo: DailyTransactionRepository | None = None,
        bank_repo: BankTransactionRepository | None = None,
        payment_repo: DailyTransactionPaymentRepository | None = None,
        master_repo: MasterRepository | None = None,
    ):
        self.repo = repository or ECourtRepository()
        self.daily_repo = daily_repo or DailyTransactionRepository()
        self.bank_repo = bank_repo or BankTransactionRepository()
        self.payment_repo = payment_repo or DailyTransactionPaymentRepository()
        self.master_repo = master_repo or MasterRepository()
        self.pdf = ECourtPdfService()

    @staticmethod
    def _decimal(value) -> Decimal:
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("Invalid amount.") from None

    @staticmethod
    def _date(value) -> date | None:
        raw = (value or "").strip()
        if not raw:
            return None
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None

    @classmethod
    def is_importable_amount(cls, value) -> bool:
        try:
            amount = cls._decimal(value)
            return amount >= cls.MIN_IMPORT_AMOUNT and amount <= cls.MAX_IMPORT_AMOUNT
        except ValueError:
            return False

    @classmethod
    def is_high_amount(cls, value) -> bool:
        try:
            amount = cls._decimal(value)
            return amount >= cls.HIGH_AMOUNT_MIN and amount <= cls.MAX_IMPORT_AMOUNT
        except ValueError:
            return False

    @classmethod
    def is_small_amount(cls, value) -> bool:
        try:
            amount = cls._decimal(value)
            return amount >= cls.MIN_IMPORT_AMOUNT and amount <= cls.SMALL_AMOUNT_MAX
        except ValueError:
            return False

    @staticmethod
    def _generate_high_amount_stationery() -> str:
        """One auto stationery for all amount 11–500 rows in a PDF import."""
        return f"HA{datetime.now().strftime('%y%m%d%H%M%S')}"

    @staticmethod
    def _preview_row(line) -> dict:
        return {
            "receipt_no": (line.receipt_no or "").strip().upper(),
            "receipt_date": line.receipt_date.isoformat() if line.receipt_date else "",
            "amount": str(line.amount),
            "payment_mode": line.payment_mode or "",
            "receipt_status": line.receipt_status or "",
            "remarks": line.remarks or "",
            "stationerynumber": "",
            "auto_stationery": False,
            "high_amount": False,
        }

    def _normalize_import_row(
        self,
        row: dict,
        *,
        row_index: int,
        allow_any_positive_amount: bool = False,
    ) -> dict | None:
        receipt_no = (row.get("receipt_no") or row.get("ReceiptNo") or "").strip().upper()
        if not receipt_no:
            return None

        amount = self._decimal(row.get("amount") or row.get("Amount"))
        if amount < self.MIN_IMPORT_AMOUNT:
            return None
        if not allow_any_positive_amount and amount > self.MAX_IMPORT_AMOUNT:
            return None

        receipt_date = self._date(row.get("receipt_date") or row.get("ReceiptDate"))
        if not receipt_date:
            return None

        stationerynumber = (
            row.get("stationerynumber")
            or row.get("StationeryNumber")
            or row.get("StationeryNo")
            or ""
        ).strip()
        if not stationerynumber:
            return None

        payment_mode = (row.get("payment_mode") or row.get("PaymentMode") or "").strip() or None
        receipt_status = (row.get("receipt_status") or row.get("ReceiptStatus") or "").strip() or None
        remarks = (row.get("remarks") or row.get("Remarks") or "").strip() or None

        return {
            "ReceiptNo": receipt_no,
            "ReceiptDate": receipt_date,
            "Amount": amount,
            "PaymentMode": payment_mode,
            "ReceiptStatus": receipt_status,
            "Remarks": remarks,
            "StationeryNumber": stationerynumber or None,
        }

    def parse_pdf_preview(self, raw: bytes, *, file_name: str) -> dict:
        report = self.pdf.parse_pdf_bytes(raw)
        rows: list[dict] = []
        excluded_high_amount = 0
        for line in report.lines:
            if line.amount < self.MIN_IMPORT_AMOUNT or line.amount > self.MAX_IMPORT_AMOUNT:
                excluded_high_amount += 1
                continue
            rows.append(self._preview_row(line))

        small_rows: list[dict] = []
        high_rows: list[dict] = []
        for row in rows:
            if self.is_high_amount(row.get("amount")):
                high_rows.append(row)
            else:
                small_rows.append(row)

        auto_stationery = None
        if high_rows:
            auto_stationery = self._generate_high_amount_stationery()
            for row in high_rows:
                row["stationerynumber"] = auto_stationery
                row["auto_stationery"] = True
                row["high_amount"] = True

        rows = small_rows + high_rows

        if not rows:
            raise ValueError(
                f"No receipts with amount {self.MIN_IMPORT_AMOUNT}–{self.MAX_IMPORT_AMOUNT} found in PDF. "
                f"{excluded_high_amount} row(s) excluded (outside amount range)."
            )

        pdf_record_count = report.record_count or len(report.lines)
        message = (
            f"Read {len(rows)} receipt(s) for review "
            f"(amount {self.MIN_IMPORT_AMOUNT}–{self.MAX_IMPORT_AMOUNT}). "
            f"{len(small_rows)} small (≤{self.SMALL_AMOUNT_MAX}) — stationery on row 1, 21, 41… + Apply next 20."
        )
        if high_rows:
            message += (
                f" {len(high_rows)} high ({self.HIGH_AMOUNT_MIN}–{self.MAX_IMPORT_AMOUNT}) — "
                f"auto stationery {auto_stationery} (same for all, disabled)."
            )
        if excluded_high_amount:
            message += (
                f" {excluded_high_amount} row(s) outside amount "
                f"{self.MIN_IMPORT_AMOUNT}–{self.MAX_IMPORT_AMOUNT} excluded."
            )
        if pdf_record_count and pdf_record_count != len(rows) + excluded_high_amount:
            message += f" PDF record count: {pdf_record_count}."

        receipt_numbers = [row["receipt_no"] for row in rows if row.get("receipt_no")]
        existing_details = self.repo.existing_imported_receipt_details(receipt_numbers)
        existing_imported_receipts = sorted(
            existing_details.values(),
            key=lambda item: item["receipt_no"],
        )
        if existing_imported_receipts:
            message += f" {len(existing_imported_receipts)} receipt number(s) already in database."

        return {
            "file_name": file_name,
            "report_from": report.report_from.isoformat() if report.report_from else "",
            "report_to": report.report_to.isoformat() if report.report_to else "",
            "state_name": report.state_name or "",
            "total_amount": str(report.total_amount or ""),
            "record_count": len(rows),
            "pdf_record_count": pdf_record_count,
            "excluded_high_amount": excluded_high_amount,
            "max_amount": str(self.MAX_IMPORT_AMOUNT),
            "min_amount": str(self.MIN_IMPORT_AMOUNT),
            "existing_imported_receipts": existing_imported_receipts,
            "existing_receipt_numbers": [item["receipt_no"] for item in existing_imported_receipts],
            "rows": rows,
            "message": message,
        }

    def _row_stationery(self, row: dict) -> str:
        return (
            row.get("stationerynumber")
            or row.get("StationeryNumber")
            or row.get("StationeryNo")
            or ""
        ).strip()

    def _is_high_amount_preview_row(self, row: dict) -> bool:
        if row.get("high_amount") or row.get("auto_stationery"):
            return True
        amount_raw = row.get("amount") if row.get("amount") is not None else row.get("Amount")
        return self.is_high_amount(amount_raw)

    def validate_import_preview(self, rows: list[dict]) -> tuple[list[dict], int]:
        errors: list[str] = []
        stationery_block_map: dict[str, int] = {}
        candidate_rows: list[tuple[int, dict]] = []

        small_indexed: list[tuple[int, dict]] = []
        high_indexed: list[tuple[int, dict]] = []
        for idx, row in enumerate(rows):
            if row.get("already_imported"):
                continue
            row_num = idx + 1
            if self._is_high_amount_preview_row(row):
                high_indexed.append((row_num, row))
            else:
                small_indexed.append((row_num, row))

        # Amount ≤10: existing 20-row stationery blocks
        for block_idx, block_start in enumerate(range(0, len(small_indexed), self.BLOCK_SIZE)):
            block = small_indexed[block_start : block_start + self.BLOCK_SIZE]
            block_num = block_idx + 1
            row_nums = [rn for rn, _ in block]
            row_start = row_nums[0] if row_nums else block_start + 1
            row_end = row_nums[-1] if row_nums else row_start
            block_stationeries: set[str] = set()
            block_complete: list[tuple[int, dict]] = []
            partial_row_nums: list[int] = []
            has_any_data = False
            block_has_stationery = False

            for row_num, row in block:
                receipt_no = (row.get("receipt_no") or row.get("ReceiptNo") or "").strip()
                receipt_date = (row.get("receipt_date") or row.get("ReceiptDate") or "").strip()
                amount_raw = row.get("amount") if row.get("amount") is not None else row.get("Amount")
                stationery = self._row_stationery(row)

                if not receipt_no and not receipt_date and amount_raw in (None, "") and not stationery:
                    continue

                has_any_data = True
                if stationery:
                    block_has_stationery = True
                missing: list[str] = []
                if not receipt_no:
                    missing.append("receipt no")
                if not receipt_date:
                    missing.append("date")
                if amount_raw in (None, "") or not self.is_importable_amount(amount_raw):
                    missing.append("amount")
                if not stationery:
                    missing.append("stationery number")

                if missing:
                    partial_row_nums.append(row_num)
                    continue

                block_complete.append((row_num, row))
                block_stationeries.add(stationery)

            if not has_any_data or not block_has_stationery:
                continue

            if partial_row_nums:
                errors.append(
                    f"Block {block_num} (rows {row_start}-{row_end}): rows {partial_row_nums} "
                    "have blank receipt no, date, amount or stationery number."
                )
            elif block_complete and len(block_stationeries) > 1:
                values = ", ".join(sorted(block_stationeries))
                errors.append(
                    f"Block {block_num} (rows {row_start}-{row_end}): "
                    f"all rows must have the same stationery number (found: {values})."
                )
            elif block_complete and len(block_stationeries) == 1:
                stationery = next(iter(block_stationeries))
                if stationery in stationery_block_map:
                    prev_block = stationery_block_map[stationery]
                    errors.append(
                        f"Duplicate stationery number '{stationery}' in block {block_num} and block {prev_block}."
                    )
                else:
                    stationery_block_map[stationery] = block_num
                candidate_rows.extend(block_complete)

        # Amount 11–500: each row is its own entry; shared auto stationery allowed
        high_stationeries: set[str] = set()
        high_complete: list[tuple[int, dict]] = []
        high_partial: list[int] = []
        for row_num, row in high_indexed:
            receipt_no = (row.get("receipt_no") or row.get("ReceiptNo") or "").strip()
            receipt_date = (row.get("receipt_date") or row.get("ReceiptDate") or "").strip()
            amount_raw = row.get("amount") if row.get("amount") is not None else row.get("Amount")
            stationery = self._row_stationery(row)

            if not receipt_no and not receipt_date and amount_raw in (None, "") and not stationery:
                continue

            missing: list[str] = []
            if not receipt_no:
                missing.append("receipt no")
            if not receipt_date:
                missing.append("date")
            if amount_raw in (None, "") or not self.is_importable_amount(amount_raw):
                missing.append("amount")
            if not stationery:
                missing.append("stationery number")

            if missing:
                high_partial.append(row_num)
                continue

            high_complete.append((row_num, row))
            high_stationeries.add(stationery)

        if high_partial:
            errors.append(
                f"High-amount rows {high_partial}: blank receipt no, date, amount or stationery number."
            )
        elif high_complete:
            if len(high_stationeries) > 1:
                values = ", ".join(sorted(high_stationeries))
                errors.append(
                    f"All amount {self.HIGH_AMOUNT_MIN}–{self.MAX_IMPORT_AMOUNT} rows must share "
                    f"one auto stationery number (found: {values})."
                )
            else:
                stationery = next(iter(high_stationeries))
                if stationery in stationery_block_map:
                    prev_block = stationery_block_map[stationery]
                    errors.append(
                        f"Duplicate stationery number '{stationery}' used by high-amount rows "
                        f"and small-amount block {prev_block}."
                    )
                else:
                    candidate_rows.extend(high_complete)

        if errors:
            raise ValueError("Import validation failed:\n" + "\n".join(errors))

        if not candidate_rows:
            raise ValueError(
                "No rows ready to import. For amount ≤10 enter stationery on row 1, 21, 41… "
                "and Apply next 20; amount 11–500 use auto stationery."
            )

        line_rows: list[dict] = []
        dup_errors: list[str] = []
        seen_composite: set[tuple] = set()
        seen_receipts: set[str] = set()

        for row_num, row in candidate_rows:
            normalized = self._normalize_import_row(row, row_index=row_num)
            if normalized is None:
                dup_errors.append(f"Row {row_num}: missing receipt no, date, amount or stationery number.")
                continue

            composite = (
                normalized["ReceiptNo"],
                normalized["ReceiptDate"].isoformat(),
                str(normalized["Amount"]),
                normalized["StationeryNumber"] or "",
            )
            if composite in seen_composite:
                dup_errors.append(
                    f"Row {row_num}: duplicate receipt no + date + amount + stationery number."
                )
            seen_composite.add(composite)

            if normalized["ReceiptNo"] in seen_receipts:
                dup_errors.append(f"Row {row_num}: duplicate receipt number {normalized['ReceiptNo']}.")
            seen_receipts.add(normalized["ReceiptNo"])

            line_rows.append(normalized)

        if dup_errors:
            raise ValueError("Import validation failed:\n" + "\n".join(dup_errors))

        skipped_count = max(len(rows) - len(line_rows), 0)
        return line_rows, skipped_count

    def prepare_import_rows(
        self, rows: list[dict], *, allow_any_positive_amount: bool = False
    ) -> list[dict]:
        """Import only rows with receipt no, date, amount and stationery filled."""
        candidate_receipts = [
            (row.get("receipt_no") or row.get("ReceiptNo") or "").strip().upper()
            for row in rows
            if not row.get("already_imported")
        ]
        existing_receipts = self.repo.existing_receipt_numbers_in_db(
            [value for value in candidate_receipts if value]
        )

        line_rows: list[dict] = []
        dup_errors: list[str] = []
        seen_composite: set[tuple] = set()
        seen_receipts: set[str] = set()

        for row_num, row in enumerate(rows, start=1):
            if row.get("already_imported"):
                continue

            normalized = self._normalize_import_row(
                row,
                row_index=row_num,
                allow_any_positive_amount=allow_any_positive_amount,
            )
            if normalized is None:
                continue

            if normalized["ReceiptNo"] in existing_receipts:
                continue

            composite = (
                normalized["ReceiptNo"],
                normalized["ReceiptDate"].isoformat(),
                str(normalized["Amount"]),
                normalized["StationeryNumber"] or "",
            )
            if composite in seen_composite:
                dup_errors.append(
                    f"Row {row_num}: duplicate receipt no + date + amount + stationery number."
                )
            seen_composite.add(composite)

            if normalized["ReceiptNo"] in seen_receipts:
                dup_errors.append(f"Row {row_num}: duplicate receipt number {normalized['ReceiptNo']}.")
            seen_receipts.add(normalized["ReceiptNo"])

            line_rows.append(normalized)

        if dup_errors:
            raise ValueError("Import validation failed:\n" + "\n".join(dup_errors))

        if not line_rows:
            raise ValueError(
                "No rows to import. For amount ≤10 enter stationery on 1/21/41… and Apply next 20; "
                "amount 11–500 use auto stationery."
            )

        return line_rows

    def import_rows(
        self, payload: dict, *, imported_by: str, allow_any_positive_amount: bool = False
    ) -> dict:
        rows = payload.get("rows") or []
        if not rows:
            raise ValueError("No rows to import.")

        file_name = (payload.get("file_name") or "import.pdf").strip() or "import.pdf"
        line_rows = self.prepare_import_rows(
            rows, allow_any_positive_amount=allow_any_positive_amount
        )
        skipped_count = int(payload.get("skipped_count") or 0)

        candidate_receipts = [row["ReceiptNo"] for row in line_rows]
        existing_receipts = self.repo.existing_receipt_numbers_in_db(candidate_receipts)

        to_insert: list[dict] = []
        skipped_duplicates: list[dict] = []
        for row in line_rows:
            if row["ReceiptNo"] in existing_receipts:
                skipped_duplicates.append(
                    {
                        "receipt_no": row["ReceiptNo"],
                        "stationerynumber": row["StationeryNumber"] or "",
                        "reason": "Receipt number already exists in database.",
                    }
                )
            else:
                to_insert.append(row)

        if not to_insert:
            raise ValueError(
                "No new rows to import. All "
                f"{len(skipped_duplicates)} row(s) already exist (duplicate receipt number)."
            )

        total_amount = payload.get("total_amount")
        total_decimal: Decimal | None = None
        if total_amount not in (None, ""):
            total_decimal = self._decimal(total_amount)

        report_from = self._date(payload.get("report_from"))
        report_to = self._date(payload.get("report_to"))
        batch = self.repo.create_batch(
            {
                "FileName": file_name,
                "ReportFrom": report_from,
                "ReportTo": report_to,
                "StateName": (payload.get("state_name") or "").strip() or None,
                "TotalAmount": total_decimal,
                "RecordCount": len(to_insert),
                "ImportedBy": imported_by,
            }
        )
        self.repo.add_lines(batch.ImportID, to_insert)

        message = f"Imported {len(to_insert)} receipt(s)."
        if skipped_duplicates:
            message += f" {len(skipped_duplicates)} duplicate(s) not imported."

        return {
            "import_id": batch.ImportID,
            "file_name": batch.FileName,
            "record_count": len(to_insert),
            "skipped_count": skipped_count,
            "duplicate_count": len(skipped_duplicates),
            "skipped_duplicates": skipped_duplicates,
            "total_amount": str(total_decimal or ""),
            "report_from": payload.get("report_from") or "",
            "report_to": payload.get("report_to") or "",
            "message": message,
        }

    def search_stationery(self, stationery_no: str, *, import_id: int | None = None) -> dict:
        normalized = (stationery_no or "").strip()
        if not normalized:
            raise ValueError("Stationery number is required.")

        lines = self.repo.list_lines_for_stationery(normalized, import_id=import_id)
        if not lines:
            return {
                "import_id": import_id,
                "stationery_no": normalized,
                "summary_status": self.NOT_SOLD,
                "total_receipts": 0,
                "sold_count": 0,
                "not_sold_count": 0,
                "rows": [],
                "message": f"No receipts found for stationery {normalized}.",
            }

        receipt_numbers = [line.ReceiptNo for line in lines]
        sold_set = {(value or "").strip().upper() for value in self.repo.sold_receipt_numbers(receipt_numbers)}
        txn_dates = self.repo.transaction_dates_by_receipt(receipt_numbers)
        account_map = self.repo.account_numbers_by_receipt(receipt_numbers)
        rows: list[dict] = []
        sold_count = 0
        for line in lines:
            receipt_key = (line.ReceiptNo or "").strip().upper()
            is_sold = receipt_key in sold_set
            if is_sold:
                sold_count += 1
            receipt_date = line.ReceiptDate.isoformat() if line.ReceiptDate else ""
            transaction_date = txn_dates.get(receipt_key, "") if is_sold else ""
            account_number = account_map.get(receipt_key, "") if is_sold else ""
            rows.append(
                {
                    "receipt_no": line.ReceiptNo,
                    "receipt_date": receipt_date,
                    "transaction_date": transaction_date,
                    "display_date": transaction_date or receipt_date,
                    "amount": str(line.Amount),
                    "payment_mode": line.PaymentMode or "",
                    "receipt_status": line.ReceiptStatus or "",
                    "remarks": line.Remarks or "",
                    "stationerynumber": line.StationeryNumber or "",
                    "account_number": account_number,
                    "sale_status": self.SOLD if is_sold else self.NOT_SOLD,
                }
            )

        total = len(rows)
        if sold_count == 0:
            summary = self.NOT_SOLD
        elif sold_count == total:
            summary = self.SOLD
        else:
            summary = self.PARTIALLY_SOLD

        return {
            "import_id": import_id,
            "stationery_no": normalized,
            "summary_status": summary,
            "total_receipts": total,
            "sold_count": sold_count,
            "not_sold_count": total - sold_count,
            "rows": rows,
            "message": f"Stationery {normalized}: {summary} ({sold_count} of {total} sold).",
        }

    def _summary_status(self, sold_count: int, total: int) -> str:
        if sold_count == 0:
            return self.NOT_SOLD
        if sold_count == total:
            return self.SOLD
        return self.PARTIALLY_SOLD

    def _group_sell_amount(self, sold_receipt_numbers: list[str]) -> Decimal:
        sales = self.repo.list_sales_for_receipts(sold_receipt_numbers)
        daily_ids = {sale.DailyTransactionID for sale in sales if sale.DailyTransactionID}
        total = Decimal("0")
        for daily_id in daily_ids:
            daily = self.daily_repo.get_by_id(daily_id)
            if daily is not None and daily.SaleAmount is not None:
                total += Decimal(str(daily.SaleAmount))
        return total

    @staticmethod
    def _money_text(value: Decimal) -> str:
        quantized = value.quantize(Decimal("0.01"))
        if quantized == quantized.to_integral_value():
            return str(int(quantized))
        return format(quantized, "f")

    def _attach_group_sale_values(self, group: dict, receipts: list[dict]) -> None:
        sold_receipts = [row for row in receipts if row["sale_status"] == self.SOLD]
        sold_numbers = [row["receipt_no"] for row in sold_receipts if row.get("receipt_no")]
        summary = group.get("summary_status")

        sell_dates = sorted(
            {
                (row.get("transaction_date") or "").strip()
                for row in sold_receipts
                if (row.get("transaction_date") or "").strip()
            }
        )
        if sell_dates:
            # One bulk sell → one date; multiple sells → latest transaction date on parent.
            group["transaction_date"] = sell_dates[-1] if len(sell_dates) > 1 else sell_dates[0]
            group["sell_date"] = group["transaction_date"]
        else:
            group["transaction_date"] = ""
            group["sell_date"] = ""

        account_numbers: list[str] = []
        for row in sold_receipts:
            acc = (row.get("account_number") or "").strip()
            if acc and acc not in account_numbers:
                account_numbers.append(acc)
        group["account_number"] = ", ".join(account_numbers)
        group["account_numbers"] = account_numbers

        buy_total = sum(self._decimal(row.get("amount") or "0") for row in receipts)
        group["total_buy_value"] = self._money_text(buy_total)

        if summary == self.SOLD:
            sell_total = self._group_sell_amount(sold_numbers)
            group["total_sell_value"] = self._money_text(sell_total)
            return

        if summary == self.PARTIALLY_SOLD:
            sold_buy = sum(self._decimal(row.get("amount") or "0") for row in sold_receipts)
            sell_total = self._group_sell_amount(sold_numbers)
            group["sold_buy_value"] = self._money_text(sold_buy)
            group["sold_sell_value"] = self._money_text(sell_total)
            group["remaining_receipts"] = group.get("not_sold_count", 0)
            return

        # Not Sold — buy value is known from import; sell value stays empty.
        group["total_sell_value"] = ""

    def _build_import_tree_groups(self, lines: list) -> tuple[list[dict], int]:
        if not lines:
            return [], 0

        receipt_numbers = [line.ReceiptNo for line in lines]
        sold_set = {(value or "").strip().upper() for value in self.repo.sold_receipt_numbers(receipt_numbers)}
        txn_dates = self.repo.transaction_dates_by_receipt(receipt_numbers)
        account_map = self.repo.account_numbers_by_receipt(receipt_numbers)
        grouped: dict[str, list[dict]] = {}

        for line in lines:
            stationery = (line.StationeryNumber or "").strip() or "(blank)"
            receipt_key = (line.ReceiptNo or "").strip().upper()
            is_sold = receipt_key in sold_set
            receipt_date = line.ReceiptDate.isoformat() if line.ReceiptDate else ""
            transaction_date = txn_dates.get(receipt_key, "") if is_sold else ""
            account_number = account_map.get(receipt_key, "") if is_sold else ""
            grouped.setdefault(stationery, []).append(
                {
                    "receipt_no": line.ReceiptNo,
                    "receipt_date": receipt_date,
                    "transaction_date": transaction_date,
                    "display_date": transaction_date or receipt_date,
                    "amount": str(line.Amount),
                    "payment_mode": line.PaymentMode or "",
                    "receipt_status": line.ReceiptStatus or "",
                    "remarks": line.Remarks or "",
                    "stationerynumber": line.StationeryNumber or "",
                    "account_number": account_number,
                    "sale_status": self.SOLD if is_sold else self.NOT_SOLD,
                }
            )

        groups: list[dict] = []
        for stationery in sorted(grouped.keys()):
            receipts = grouped[stationery]
            sold_count = sum(1 for row in receipts if row["sale_status"] == self.SOLD)
            total = len(receipts)
            group = {
                "stationerynumber": stationery,
                "total_receipts": total,
                "sold_count": sold_count,
                "not_sold_count": total - sold_count,
                "summary_status": self._summary_status(sold_count, total),
                "receipts": receipts,
            }
            self._attach_group_sale_values(group, receipts)
            groups.append(group)

        return groups, len(lines)

    def list_import_tree(self, import_id: int | None = None) -> dict:
        if import_id is not None:
            batch = self.repo.get_batch(import_id)
            if batch is None:
                raise ValueError(f"Import #{import_id} not found.")
            lines = self.repo.list_lines_for_import(batch.ImportID)
            groups, total = self._build_import_tree_groups(lines)
            if not groups:
                return {
                    "scope": "import",
                    "import_id": batch.ImportID,
                    "file_name": batch.FileName or "",
                    "total_receipts": 0,
                    "group_count": 0,
                    "groups": [],
                    "message": "No imported receipts in this batch.",
                }
            return {
                "scope": "import",
                "import_id": batch.ImportID,
                "file_name": batch.FileName or "",
                "total_receipts": total,
                "group_count": len(groups),
                "groups": groups,
                "message": f"Loaded {total} receipt(s) in {len(groups)} stationery group(s) from import #{batch.ImportID}.",
            }

        lines = self.repo.list_all_lines()
        if not lines:
            return {
                "scope": "all",
                "import_id": None,
                "file_name": "",
                "total_receipts": 0,
                "group_count": 0,
                "groups": [],
                "message": "No receipts yet. Use Import PDF or Manual Entry.",
            }

        latest = self.repo.latest_batch()
        groups, total = self._build_import_tree_groups(lines)
        return {
            "scope": "all",
            "import_id": latest.ImportID if latest else None,
            "file_name": "",
            "total_receipts": total,
            "group_count": len(groups),
            "groups": groups,
            "message": f"Loaded {total} receipt(s) in {len(groups)} stationery group(s) across all imports.",
        }

    def _collect_bank_rows_for_daily(self, daily: JTCSDailyTransaction) -> list:
        payment_rows = self.payment_repo.list_by_transaction(daily.TransactionID)
        bank_rows = self.bank_repo.find_all_by_daily_id(daily.TransactionID)
        seen = {row.JtcsBankTransactionID for row in bank_rows}
        for payment_row in payment_rows:
            bank_id = payment_row.BankTransactionID
            if bank_id and bank_id not in seen:
                bank_row = self.bank_repo.get_by_id(bank_id)
                if bank_row is not None:
                    bank_rows.append(bank_row)
                    seen.add(bank_row.JtcsBankTransactionID)
        if daily.BankTransactionID and daily.BankTransactionID not in seen:
            bank_row = self.bank_repo.get_by_id(daily.BankTransactionID)
            if bank_row is not None:
                bank_rows.append(bank_row)
        return bank_rows

    def _remove_ecourt_daily(self, daily: JTCSDailyTransaction) -> None:
        bank_rows = self._collect_bank_rows_for_daily(daily)
        self.payment_repo.delete_by_transaction(daily.TransactionID)
        daily.BankTransactionID = None
        db.session.flush()
        for bank_row in bank_rows:
            self.bank_repo.delete(bank_row)
        self.daily_repo.delete(daily)

    def delete_unsold_stationery(self, stationery_no: str) -> dict:
        """Delete imported receipt lines for a stationery that is fully Not Sold."""
        normalized = (stationery_no or "").strip()
        if not normalized:
            raise ValueError("Stationery number is required.")

        lines = self.repo.list_lines_for_stationery(normalized, exact=True)
        if not lines:
            raise ValueError(f"Stationery '{normalized}' not found.")

        # Guard against LIKE-style mismatches: only exact stationery number.
        lines = [
            line
            for line in lines
            if (line.StationeryNumber or "").strip() == normalized
        ]
        if not lines:
            raise ValueError(f"Stationery '{normalized}' not found.")

        receipt_numbers = sorted(
            {
                (line.ReceiptNo or "").strip().upper()
                for line in lines
                if (line.ReceiptNo or "").strip()
            }
        )
        sold = self.repo.sold_receipt_numbers(receipt_numbers)
        if sold:
            sample = ", ".join(sorted(sold)[:5])
            more = "" if len(sold) <= 5 else f" (+{len(sold) - 5} more)"
            raise ValueError(
                f"Cannot delete stationery '{normalized}': "
                f"{len(sold)} receipt(s) are Sold. Unsold first. Examples: {sample}{more}"
            )

        import_ids = [line.ImportID for line in lines if line.ImportID]
        deleted = self.repo.delete_lines(lines)
        self.repo.delete_empty_batches(import_ids)
        return {
            "stationerynumber": normalized,
            "record_count": deleted,
            "message": f"Deleted stationery '{normalized}' ({deleted} receipt(s)).",
        }

    def unsell_receipts(self, receipt_numbers: list[str]) -> dict:
        """Roll back sold e-Court receipts (sale rows + daily + bank ledger)."""
        normalized = sorted(
            {(value or "").strip().upper() for value in receipt_numbers if (value or "").strip()}
        )
        if not normalized:
            raise ValueError("Select at least one sold receipt to unsell.")

        sales = self.repo.list_sales_for_receipts(normalized)
        if not sales:
            raise ValueError("No sold receipts found to unsell.")

        daily_ids = sorted(
            {int(sale.DailyTransactionID) for sale in sales if sale.DailyTransactionID}
        )
        orphan_sales = [sale for sale in sales if not sale.DailyTransactionID]

        rolled_receipts: list[str] = []
        for daily_id in daily_ids:
            daily = self.daily_repo.get_by_id(daily_id)
            if daily is None:
                continue
            sub_work = (daily.SubWorkType or "").strip()
            if sub_work and sub_work != self.SUB_WORK_TYPE:
                raise ValueError(
                    f"Daily Transaction #{daily_id} is not an e-Court Activity sale."
                )

            daily_sales = self.repo.list_sales_for_daily(daily_id)
            for sale in daily_sales:
                rolled_receipts.append(sale.ReceiptNo)
                self.repo.delete_sale(sale)
            self._remove_ecourt_daily(daily)

        for sale in orphan_sales:
            rolled_receipts.append(sale.ReceiptNo)
            self.repo.delete_sale(sale)

        unique_receipts = sorted({(r or "").strip().upper() for r in rolled_receipts if r})
        return {
            "record_count": len(unique_receipts),
            "receipts": unique_receipts,
            "message": f"Unsold {len(unique_receipts)} receipt(s). Sale rolled back.",
        }

    def _create_manual_receipt_lines(self, form: dict, receipt_numbers: list[str], *, created_by: str) -> None:
        """Insert receipt lines for Manual Entry when PDF import was skipped."""
        normalized = sorted(
            {(value or "").strip().upper() for value in receipt_numbers if (value or "").strip()}
        )
        if not normalized:
            raise ValueError("Receipt number is required for manual entry.")

        stationery = (
            form.get("ManualStationeryNumber")
            or form.get("StationeryNumber")
            or form.get("StationeryNo")
            or ""
        ).strip()
        if not stationery:
            raise ValueError("Stationery number is required for manual entry.")
        if len(stationery) > 20:
            raise ValueError("Stationery number must be at most 20 characters.")

        buy_amount = self._decimal(
            form.get("ReceiptBuyAmount")
            or form.get("ManualAmount")
            or form.get("BuyAmount")
            or form.get("Amount")
        )
        if buy_amount < self.MIN_IMPORT_AMOUNT:
            raise ValueError("Receipt amount must be at least 1 for manual entry.")

        receipt_date = (
            self._date(form.get("ManualReceiptDate") or form.get("ReceiptDate")) or date.today()
        )
        remarks = (form.get("ManualRemarks") or form.get("Remarks") or "").strip() or None

        total = (buy_amount * len(normalized)).quantize(Decimal("0.01"))
        batch = self.repo.create_batch(
            {
                "FileName": "manual-entry",
                "TotalAmount": total,
                "RecordCount": len(normalized),
                "ImportedBy": created_by,
            }
        )
        self.repo.add_lines(
            batch.ImportID,
            [
                {
                    "ReceiptNo": receipt_no,
                    "ReceiptDate": receipt_date,
                    "Amount": buy_amount,
                    "PaymentMode": None,
                    "ReceiptStatus": "Manual Entry",
                    "Remarks": remarks,
                    "StationeryNumber": stationery,
                }
                for receipt_no in normalized
            ],
        )

    def save_manual_import(self, form: dict, *, imported_by: str) -> dict:
        """Import one receipt into the stationery tree (PDF Import–style, no sale)."""
        receipt_no = (form.get("ReceiptNo") or "").strip().upper()
        stationery = (form.get("StationeryNumber") or form.get("StationeryNo") or "").strip()
        amount_raw = form.get("Amount") or form.get("amount") or ""
        receipt_date = (form.get("ReceiptDate") or "").strip() or date.today().isoformat()
        remarks = (form.get("Remarks") or "").strip()

        if not receipt_no:
            raise ValueError("Receipt number is required.")
        if not stationery:
            raise ValueError("Stationery Number is required.")
        if len(stationery) > 20:
            raise ValueError("Stationery number must be at most 20 characters.")

        amount = self._decimal(amount_raw)
        if amount < self.MIN_IMPORT_AMOUNT:
            raise ValueError(f"Amount must be at least {self.MIN_IMPORT_AMOUNT}.")

        existing_stn = self.repo.list_lines_for_stationery(stationery, exact=True)
        if existing_stn:
            raise ValueError(
                f"Stationery number '{stationery}' already exists in main table "
                f"({len(existing_stn)} receipt(s)). Choose another."
            )

        existing_receipts = self.repo.existing_receipt_numbers_in_db([receipt_no])
        if existing_receipts:
            raise ValueError(f"Receipt number '{receipt_no}' already imported.")

        result = self.import_rows(
            {
                "file_name": "manual-entry",
                "total_amount": str(amount),
                "rows": [
                    {
                        "receipt_no": receipt_no,
                        "receipt_date": receipt_date,
                        "amount": str(amount),
                        "payment_mode": "",
                        "receipt_status": "Manual Entry",
                        "remarks": remarks,
                        "stationerynumber": stationery,
                    }
                ],
            },
            imported_by=imported_by,
            allow_any_positive_amount=True,
        )
        result["stationerynumber"] = stationery
        result["message"] = (
            f"Import Successfully — {receipt_no} under stationery {stationery}."
        )
        return result

    def save_manual_sale(self, form: dict, *, created_by: str) -> dict:
        """Legacy CLI helper: import if missing, then sell. Prefer save_manual_import for UI."""
        receipt_no = (form.get("ReceiptNo") or "").strip().upper()
        if not receipt_no:
            raise ValueError("Receipt number is required.")
        existing = self.repo.get_lines_by_receipts([receipt_no])
        if not existing:
            self.save_manual_import(form, imported_by=created_by)
        return self.save_receipt_sales(form, [receipt_no], created_by=created_by)

    @staticmethod
    def _get_form_list(form: dict, key: str) -> list:
        if hasattr(form, "getlist"):
            return list(form.getlist(key) or [])
        value = form.get(key)
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            return list(value)
        return [value]

    def _parse_payment_lines(self, form: dict, sale_amount: Decimal) -> list[dict]:
        bank_ids = self._get_form_list(form, "PaymentBankAccountID[]")
        amounts = self._get_form_list(form, "PaymentAmount[]")

        if not bank_ids:
            single_bank = form.get("BankAccountID") or form.get("PaymentModeID")
            if single_bank:
                bank_ids = [single_bank]
                amounts = [str(sale_amount)]

        if not bank_ids:
            return []

        if len(amounts) < len(bank_ids):
            amounts.extend([""] * (len(bank_ids) - len(amounts)))

        lines: list[dict] = []
        total = Decimal("0")
        for bank_id_raw, amount_raw in zip(bank_ids, amounts):
            bank_account_id = int(bank_id_raw or 0)
            if bank_account_id <= 0:
                raise ValueError("Each payment mode must be selected.")
            amount = self._decimal(amount_raw)
            if amount <= 0:
                raise ValueError("Each payment amount must be greater than zero.")
            payment_mode_id = self.master_repo.resolve_payment_mode_for_bank_account(bank_account_id)
            total += amount
            lines.append(
                {
                    "bank_account_id": bank_account_id,
                    "payment_mode_id": payment_mode_id,
                    "amount": amount,
                }
            )

        if total < sale_amount:
            raise ValueError(
                f"Payment total ({total}) must be greater than or equal to Sale Amount ({sale_amount})."
            )
        return lines

    def _resolve_ecourt_purchase_bank(self):
        """e-Court buy-value wallet (alias SHCILECourt).

        Account Number / Bank Name may be real bank details. Match alias on
        Masked Account Number and other master fields, then fall back to the
        last e-Court Purchase ledger row. Does not call list_active_bank_accounts
        (that commits the session and can drop in-flight purchase ledger rows).
        """
        account = find_ecourt_purchase_bank(self.master_repo.session)
        if account is None:
            raise ValueError(
                "e-Court purchase bank account not found in Bank Master. "
                "Use account number HUKECFUK1423304 (SHCIL-e-Court) for e-Court purchase."
            )
        return self.master_repo.resolve_bank_account_by_id(account.JtcsBankAccountID)

    def save_receipt_sales(self, form: dict, receipt_numbers: list[str], *, created_by: str) -> dict:
        normalized_receipts = sorted({(value or "").strip().upper() for value in receipt_numbers if (value or "").strip()})
        if not normalized_receipts:
            raise ValueError("Select at least one receipt to sell.")

        lines = self.repo.get_lines_by_receipts(normalized_receipts)
        found = {line.ReceiptNo for line in lines}
        missing = [receipt for receipt in normalized_receipts if receipt not in found]
        manual_create = str(form.get("ManualCreate") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
            "on",
        }
        if missing and manual_create:
            self._create_manual_receipt_lines(form, missing, created_by=created_by)
            lines = self.repo.get_lines_by_receipts(normalized_receipts)
            found = {line.ReceiptNo for line in lines}
            missing = [receipt for receipt in normalized_receipts if receipt not in found]
        if missing:
            raise ValueError(f"Receipt(s) not found in import data: {', '.join(missing)}.")

        sold_set = self.repo.sold_receipt_numbers(normalized_receipts)
        already_sold = [receipt for receipt in normalized_receipts if receipt in sold_set]
        if already_sold:
            raise ValueError(f"Receipt(s) already sold: {', '.join(already_sold)}.")

        sale_amount = self._decimal(form.get("SaleAmount") or form.get("Amount"))
        if sale_amount <= 1:
            raise ValueError("Sale amount must be greater than 1.")

        payment_lines = self._parse_payment_lines(form, sale_amount)
        if not payment_lines:
            raise ValueError("At least one payment mode is required.")

        txn_date = self._date(form.get("TransactionDate")) or date.today()
        customer_name = (form.get("CustomerName") or "").strip() or None
        mobile_number = (form.get("MobileNumber") or "").strip() or None
        remarks = (form.get("Remarks") or "").strip() or None

        stationery_numbers = sorted(
            {(line.StationeryNumber or "").strip() for line in lines if (line.StationeryNumber or "").strip()}
        )
        if len(stationery_numbers) == 1:
            reference_no = stationery_numbers[0]
        elif len(stationery_numbers) > 1:
            reference_no = f"{stationery_numbers[0]} +{len(stationery_numbers) - 1}"
        else:
            reference_no = normalized_receipts[0]

        if len(normalized_receipts) == 1:
            description = f"e-Court Receipt Sale — {normalized_receipts[0]}"
        else:
            description = f"e-Court Receipt Sale — {len(normalized_receipts)} receipt(s)"

        # Buy value = imported receipt amount (reconcile to PurchaseAmount + SHCILECourt ledger)
        purchase_amount = sum(
            (self._decimal(line.Amount) for line in lines),
            Decimal("0"),
        ).quantize(Decimal("0.01"))

        daily = self.daily_repo.create(
            {
                "TransactionDate": txn_date,
                "WorkType": self.WORK_TYPE,
                "SubWorkType": self.SUB_WORK_TYPE,
                "CustomerName": customer_name,
                "ReferenceNo": reference_no,
                "Description": description,
                "IncomeAmount": Decimal("0"),
                "ExpenseAmount": Decimal("0"),
                "SaleAmount": sale_amount,
                "PurchaseAmount": purchase_amount,
                "GSTAmount": Decimal("0"),
                "TDSAmount": Decimal("0"),
                "TotalAmount": sale_amount,
                "PaymentModeID": payment_lines[0]["payment_mode_id"],
                "PaymentSplitCount": len(payment_lines),
                "Status": "Posted",
                "CreatedBy": created_by,
                "CreatedDate": datetime.utcnow(),
                "Remarks": remarks,
            }
        )

        bank_ids: list[int] = []
        for index, payment_line in enumerate(payment_lines, start=1):
            bank_account = self.master_repo.resolve_bank_account_by_id(payment_line["bank_account_id"])
            bank = self.bank_repo.create(
                {
                    "JtcsBankAccountID": bank_account.account_id or 0,
                    "BankName": bank_account.bank_name,
                    "MaskedAccountNumber": bank_account.masked_account_number,
                    "TransactionDate": txn_date,
                    "Description": "e-Court Receipt Sale",
                    "Debit": payment_line["amount"],
                    "Credit": None,
                    "ClosingBalance": Decimal("0"),
                    "ImportedBy": created_by,
                    "ImportedDate": datetime.utcnow(),
                    "Remarks": reference_no,
                    "IsLocked": False,
                    "SourceTable": self.bank_repo.SOURCE_TABLE,
                    "SourceRecordID": daily.TransactionID,
                    "SourceType": self.WORK_TYPE,
                    "SourceID": daily.TransactionID,
                    "LedgerKind": "RECEIPT",
                    "PaymentModeID": payment_line["payment_mode_id"],
                    "PaymentSequence": index,
                }
            )
            bank_ids.append(bank.JtcsBankTransactionID)
            self.payment_repo.create(
                {
                    "TransactionID": daily.TransactionID,
                    "PaymentSequence": index,
                    "PaymentModeID": payment_line["payment_mode_id"],
                    "BankAccountID": payment_line["bank_account_id"],
                    "Amount": payment_line["amount"],
                    "BankTransactionID": bank.JtcsBankTransactionID,
                }
            )

        # Buy amount → SHCILECourt Credit (Out), same pattern as Stamp Purchase
        if purchase_amount > 0:
            purchase_bank = self._resolve_ecourt_purchase_bank()
            purchase_mode_id = self.master_repo.resolve_payment_mode_for_bank_account(
                purchase_bank.account_id or 0
            )
            purchase_txn = self.bank_repo.create(
                {
                    "JtcsBankAccountID": purchase_bank.account_id or 0,
                    "BankName": purchase_bank.bank_name,
                    "MaskedAccountNumber": purchase_bank.masked_account_number
                    or "SHCILECourt",
                    "TransactionDate": txn_date,
                    "Description": "e-Court Purchase",
                    "Debit": None,
                    "Credit": purchase_amount,
                    "ClosingBalance": Decimal("0"),
                    "ImportedBy": created_by,
                    "ImportedDate": datetime.utcnow(),
                    "Remarks": reference_no,
                    "IsLocked": False,
                    "SourceTable": self.bank_repo.SOURCE_TABLE,
                    "SourceRecordID": daily.TransactionID,
                    "SourceType": self.WORK_TYPE,
                    "SourceID": daily.TransactionID,
                    "LedgerKind": "PAYMENT",
                    "PaymentModeID": purchase_mode_id,
                    "PaymentSequence": len(payment_lines) + 1,
                }
            )
            bank_ids.append(purchase_txn.JtcsBankTransactionID)

        if bank_ids:
            self.daily_repo.update_bank_link(daily, bank_ids[0])

        sale_rows: list[dict] = []
        for line in lines:
            sale = self.repo.create_sale(
                {
                    "ReceiptNo": line.ReceiptNo,
                    "StationeryNumber": line.StationeryNumber,
                    "ReceiptDate": line.ReceiptDate,
                    "Amount": line.Amount,
                    "CustomerName": customer_name,
                    "MobileNumber": mobile_number,
                    "Remarks": remarks,
                    "DailyTransactionID": daily.TransactionID,
                    "CreatedBy": created_by,
                }
            )
            sale_rows.append(
                {
                    "sale_id": sale.SaleID,
                    "receipt_no": sale.ReceiptNo,
                    "stationerynumber": sale.StationeryNumber or "",
                    "amount": str(sale.Amount),
                }
            )

        return {
            "daily_transaction_id": daily.TransactionID,
            "bank_transaction_ids": bank_ids,
            "record_count": len(sale_rows),
            "sale_amount": str(sale_amount),
            "purchase_amount": str(purchase_amount),
            "receipts": sale_rows,
            "message": (
                f"Sold {len(sale_rows)} receipt(s). Daily Transaction #{daily.TransactionID}."
            ),
        }

    def list_recent_sales(self) -> list[dict]:
        return [
            {
                "sale_id": row.SaleID,
                "receipt_no": row.ReceiptNo,
                "stationerynumber": row.StationeryNumber or "",
                "receipt_date": row.ReceiptDate.isoformat() if row.ReceiptDate else "",
                "amount": str(row.Amount),
                "customer_name": row.CustomerName or "",
                "mobile_number": row.MobileNumber or "",
                "created_date": row.CreatedDate.isoformat() if row.CreatedDate else "",
            }
            for row in self.repo.list_recent_sales()
        ]

    def activity_summary(self) -> dict:
        return self.repo.activity_summary()
