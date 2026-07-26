from __future__ import annotations

import csv
import io
import re
from collections import Counter
from datetime import date, datetime

from sqlalchemy import select

from app.extensions import db
from app.models.stamp import StampMaster
from app.models.transactions import JTCSDailyTransaction
from app.repositories.exceptional_stamp_upload_repository import ExceptionalStampUploadRepository

CERT_HEADER = "certificate number"
GENERATED_ON_HEADER = "generated on"
DATE_FROM_RE = re.compile(r"From\s+Date\s*:\s*(\d{2}-\d{2}-\d{4})", re.IGNORECASE)
DATE_TO_RE = re.compile(r"To\s+Date\s*:\s*(\d{2}-\d{2}-\d{4})", re.IGNORECASE)


class ExceptionalStampReportService:
    @staticmethod
    def _parse_report_date(value: str) -> date | None:
        """Parse SHCIL report / Generated On dates.

        SHCIL CSV often uses unpadded values like ``24/4/2026 10:4:40`` which
        fail strict ``%d/%m/%Y %H:%M:%S`` parsing and then fall back to the
        report From/To date — making every imported row show the same date.
        """
        raw = (value or "").strip()
        if not raw:
            return None

        candidates = [raw]
        if " " in raw:
            candidates.append(raw.split(" ", 1)[0].strip())

        # Flexible day/month (/ or -) with optional unpadded time.
        flex = re.compile(
            r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})(?:\s+(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?$"
        )
        for candidate in candidates:
            match = flex.match(candidate)
            if match:
                day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
                try:
                    return date(year, month, day)
                except ValueError:
                    continue
            for fmt in (
                "%d/%m/%Y %H:%M:%S",
                "%d-%m-%Y %H:%M:%S",
                "%d/%m/%Y %H:%M",
                "%d-%m-%Y %H:%M",
                "%d/%m/%Y",
                "%d-%m-%Y",
                "%Y-%m-%d",
                "%Y-%m-%d %H:%M:%S",
            ):
                try:
                    return datetime.strptime(candidate, fmt).date()
                except ValueError:
                    continue
        return None

    @classmethod
    def _parse_generated_on(cls, value) -> str:
        """Return ISO date (YYYY-MM-DD) from SHCIL 'Generated On' cell, or empty."""
        parsed = cls._parse_report_date(str(value or ""))
        return parsed.isoformat() if parsed else ""

    @classmethod
    def _extract_report_dates(cls, text: str) -> tuple[date | None, date | None]:
        from_match = DATE_FROM_RE.search(text or "")
        to_match = DATE_TO_RE.search(text or "")
        date_from = cls._parse_report_date(from_match.group(1)) if from_match else None
        date_to = cls._parse_report_date(to_match.group(1)) if to_match else None
        return date_from, date_to

    @staticmethod
    def _parse_stamp_duty_amount(raw) -> int:
        """Parse SHCIL stamp duty cell to whole rupees.

        SHCIL values look like ``Rs.100``, ``Rs.100.00``, ``100.00``, ``1,000.00``.
        Never strip all non-digits — that turns ``100.00`` into ``10000``.
        """
        if raw is None:
            return 0
        if isinstance(raw, bool):
            return 0
        if isinstance(raw, int):
            return raw
        if isinstance(raw, float):
            if raw != raw:  # NaN
                return 0
            return int(round(raw))

        text = str(raw).strip()
        if not text:
            return 0

        # Remove currency tokens (Rs / Rs. / Rs: / INR / ₹) anywhere in the cell.
        text = re.sub(r"(?i)(?:rs[\.:]?|inr|₹)", "", text).strip()
        text = text.replace(" ", "")
        if not text:
            return 0

        # Indian thousands: 1,00,000.50 → 100000.50 ; keep real decimal point.
        if "," in text and "." in text:
            text = text.replace(",", "")
        elif "," in text:
            # Either European decimal (100,00) or thousands (1,000)
            parts = text.split(",")
            if len(parts) == 2 and len(parts[1]) <= 2 and parts[0].lstrip("-").isdigit():
                text = parts[0] + "." + parts[1]
            else:
                text = text.replace(",", "")

        match = re.search(r"-?\d+(?:\.\d+)?", text)
        if not match:
            return 0
        try:
            return int(round(float(match.group(0))))
        except ValueError:
            return 0

    @classmethod
    def _normalize_certificate(cls, value) -> str:
        return (str(value or "")).strip().upper()

    @classmethod
    def parse_shcil_csv(cls, file_bytes: bytes, *, file_name: str = "") -> dict:
        if not file_bytes:
            raise ValueError("Uploaded file is empty.")

        decoded = None
        for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                decoded = file_bytes.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if decoded is None:
            raise ValueError("Unable to read file encoding.")

        text = decoded.replace("\r\n", "\n").replace("\r", "\n")
        date_from, date_to = cls._extract_report_dates(text)

        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        if not rows:
            raise ValueError("CSV file has no rows.")

        header_index = None
        cert_col = 1
        amount_col = 2
        generated_on_col = None
        for index, row in enumerate(rows):
            normalized = [(cell or "").strip().lower() for cell in row]
            if CERT_HEADER not in normalized:
                continue
            header_index = index
            cert_col = normalized.index(CERT_HEADER)
            if "stamp duty amount" in normalized:
                amount_col = normalized.index("stamp duty amount")
            if GENERATED_ON_HEADER in normalized:
                generated_on_col = normalized.index(GENERATED_ON_HEADER)
            # SHCIL export: Generated On is typically column K (index 10)
            if generated_on_col is None and len(row) > 10:
                generated_on_col = 10
            break

        if header_index is None:
            raise ValueError(
                'Could not find header row with "Certificate Number". '
                "Ensure this is the SHCIL E-STAMPING CSV export."
            )

        parsed_rows: list[dict] = []
        for row in rows[header_index + 1 :]:
            if not row or not any((cell or "").strip() for cell in row):
                continue
            first_cell = (row[0] or "").strip().lower()
            if first_cell.startswith("total stamp duty"):
                break

            certificate = cls._normalize_certificate(row[cert_col] if len(row) > cert_col else "")
            if not certificate:
                continue
            if not certificate.startswith("IN-"):
                continue

            amount_raw = row[amount_col] if len(row) > amount_col else ""
            stamp_duty_amount = cls._parse_stamp_duty_amount(amount_raw)
            generated_on_raw = ""
            if generated_on_col is not None and len(row) > generated_on_col:
                generated_on_raw = str(row[generated_on_col] or "").strip()
            generated_on = cls._parse_generated_on(generated_on_raw)
            parsed_rows.append(
                {
                    "certificate_number": certificate,
                    "stamp_duty_amount": stamp_duty_amount,
                    "stamp_duty_amount_raw": str(amount_raw or "").strip(),
                    "stamp_duty_type": (row[3] if len(row) > 3 else "").strip(),
                    "paid_by": (row[4] if len(row) > 4 else "").strip(),
                    "certificate_status": (row[5] if len(row) > 5 else "").strip(),
                    "generated_on": generated_on,
                    "generated_on_raw": generated_on_raw,
                    "report_date": generated_on,
                }
            )

        if not parsed_rows:
            raise ValueError("No certificate numbers found in the uploaded file.")

        counts = Counter(row["certificate_number"] for row in parsed_rows)
        duplicates = []
        seen_duplicate: set[str] = set()
        for row in parsed_rows:
            cert = row["certificate_number"]
            if counts[cert] > 1 and cert not in seen_duplicate:
                seen_duplicate.add(cert)
                duplicates.append(
                    {
                        **row,
                        "duplicate_count": counts[cert],
                    }
                )

        unique_rows = []
        seen: set[str] = set()
        for row in parsed_rows:
            cert = row["certificate_number"]
            if cert in seen:
                continue
            seen.add(cert)
            unique_rows.append(row)

        return {
            "file_name": file_name,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "csv_rows": parsed_rows,
            "csv_unique_rows": unique_rows,
            "csv_count": len(parsed_rows),
            "csv_unique_count": len(unique_rows),
            "duplicate_rows": duplicates,
            "duplicate_count": len(duplicates),
        }

    @classmethod
    def list_db_certificates(
        cls,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[dict]:
        stmt = (
            select(
                StampMaster.CertificateNumber,
                StampMaster.StampDutyAmount,
                JTCSDailyTransaction.TransactionDate,
                JTCSDailyTransaction.CustomerName,
            )
            .join(JTCSDailyTransaction, JTCSDailyTransaction.StampID == StampMaster.StampID)
            .where(
                JTCSDailyTransaction.WorkType == "SHCIL",
                JTCSDailyTransaction.SubWorkType == "Stamp Activity",
                StampMaster.IsActive == True,  # noqa: E712
            )
            .order_by(JTCSDailyTransaction.TransactionDate.desc(), StampMaster.CertificateNumber)
        )
        if date_from and date_to:
            stmt = stmt.where(
                JTCSDailyTransaction.TransactionDate >= date_from,
                JTCSDailyTransaction.TransactionDate <= date_to,
            )
        elif date_from:
            stmt = stmt.where(JTCSDailyTransaction.TransactionDate == date_from)
        elif date_to:
            stmt = stmt.where(JTCSDailyTransaction.TransactionDate == date_to)

        rows = []
        for cert, amount, txn_date, customer_name in db.session.execute(stmt).all():
            rows.append(
                {
                    "certificate_number": cls._normalize_certificate(cert),
                    "stamp_duty_amount": int(amount or 0),
                    "transaction_date": txn_date.isoformat() if txn_date else "",
                    "customer_name": (customer_name or "").strip(),
                }
            )
        return rows

    @classmethod
    def _split_previous_uploads(
        cls,
        unique_rows: list[dict],
        imported_map: dict | None = None,
    ) -> tuple[list[dict], list[dict]]:
        """Skip only certificates already present in ExceptionalStampImport."""
        previously_uploaded_rows: list[dict] = []
        new_unique_rows: list[dict] = []
        imported_map = imported_map or {}
        for row in unique_rows:
            cert = row["certificate_number"]
            imported = imported_map.get(cert)
            if imported is None:
                new_unique_rows.append(row)
                continue

            previously_uploaded_rows.append(
                {
                    **row,
                    "previous_file_name": (imported.SourceFileName or "").strip(),
                    "uploaded_date": imported.ImportedDate.isoformat()
                    if imported.ImportedDate
                    else "",
                    "uploaded_by": (imported.ImportedBy or "").strip(),
                    "report_date_from": imported.ReportDateFrom.isoformat()
                    if imported.ReportDateFrom
                    else "",
                    "report_date_to": imported.ReportDateTo.isoformat()
                    if imported.ReportDateTo
                    else "",
                    "status": "Already imported earlier",
                }
            )
        return previously_uploaded_rows, new_unique_rows

    @classmethod
    def _build_compare_sets(
        cls,
        csv_rows: list[dict],
        db_rows: list[dict],
        upload_repo: ExceptionalStampUploadRepository | None = None,
    ) -> tuple[list[dict], list[dict], list[dict]]:
        """Compare certificate sets by number.

        When ``csv_rows`` is the Final Import list, results are permanent:
        - Matched = imported ∩ JTCS
        - In CSV, not in JTCS = imported − JTCS
        - In JTCS, not in CSV = JTCS − imported
        """
        del upload_repo  # kept for call-site compatibility
        db_map = {row["certificate_number"]: row for row in db_rows}
        csv_map = {row["certificate_number"]: row for row in csv_rows}

        csv_only = []
        for cert, row in csv_map.items():
            if cert not in db_map:
                report_date = (
                    (row.get("generated_on") or "")
                    or (row.get("report_date") or "")
                    or (row.get("report_date_from") or "")
                    or (row.get("date_from") or "")
                )
                csv_only.append(
                    {
                        "certificate_number": cert,
                        "stamp_duty_amount": row["stamp_duty_amount"],
                        "stamp_duty_type": row.get("stamp_duty_type") or "",
                        "paid_by": row.get("paid_by") or "",
                        "certificate_status": row.get("certificate_status") or "",
                        "report_date": report_date[:10] if report_date else "",
                        "status": "In CSV, not in JTCS",
                    }
                )

        # Permanent: once a cert is in Final Import it is no longer "missing CSV".
        db_only_rows = []
        for cert, row in db_map.items():
            if cert in csv_map:
                continue
            db_only_rows.append(
                {
                    **row,
                    "status": "Data entry done in JTCS, CSV not uploaded",
                }
            )

        matched = []
        for cert in sorted(set(csv_map) & set(db_map)):
            csv_row = csv_map[cert]
            db_row = db_map[cert]
            matched.append(
                {
                    "certificate_number": cert,
                    "csv_stamp_duty_amount": csv_row["stamp_duty_amount"],
                    "db_stamp_duty_amount": db_row["stamp_duty_amount"],
                    "stamp_duty_amount": csv_row["stamp_duty_amount"],
                    "stamp_duty_type": csv_row.get("stamp_duty_type") or "",
                    "paid_by": csv_row.get("paid_by") or "",
                    "certificate_status": csv_row.get("certificate_status") or "",
                    "transaction_date": db_row.get("transaction_date") or "",
                    "customer_name": db_row.get("customer_name") or "",
                    "status": "Matched",
                }
            )

        return (
            matched,
            sorted(csv_only, key=lambda row: row["certificate_number"]),
            sorted(db_only_rows, key=lambda row: row["certificate_number"]),
        )

    @classmethod
    def _permanent_board(
        cls,
        upload_repo: ExceptionalStampUploadRepository,
    ) -> tuple[list[dict], list[dict], list[dict], list[dict], list[dict]]:
        """Imported Certificates vs all JTCS stamp activity (permanent cards)."""
        db_rows = cls.list_db_certificates(date_from=None, date_to=None)
        imported_rows = upload_repo.list_all_imported_rows()
        matched, csv_only, db_only_rows = cls._build_compare_sets(
            imported_rows,
            db_rows,
            upload_repo,
        )
        return imported_rows, matched, csv_only, db_only_rows, db_rows

    @classmethod
    def page_state(cls) -> dict:
        """Load all Final Import rows permanently (no date filter)."""
        upload_repo = ExceptionalStampUploadRepository()
        upload_repo.ensure_schema()

        imported_rows, matched, csv_only, db_only_rows, db_rows = cls._permanent_board(
            upload_repo
        )

        return {
            "summary": {
                "date_from": None,
                "date_to": None,
                "csv_total_rows": len(imported_rows),
                "csv_unique_rows": len(imported_rows),
                "csv_new_rows": len(imported_rows),
                "previously_uploaded": 0,
                "registered_new": len(imported_rows),
                "db_rows": len(db_rows),
                "matched": len(matched),
                "csv_only": len(csv_only),
                "db_only": len(db_only_rows),
                "duplicates_in_csv": 0,
                "imported_count": len(imported_rows),
            },
            "file_name": "Saved imports",
            "imported_rows": imported_rows,
            "db_only_rows": db_only_rows,
            "csv_only_rows": csv_only,
            "matched_rows": matched,
            "duplicate_rows": [],
            "previously_uploaded_rows": [],
        }

    @classmethod
    def compare_upload(
        cls,
        file_bytes: bytes,
        *,
        file_name: str = "",
        uploaded_by: str = "System",
    ) -> dict:
        """Parse + compare only. Does NOT save to SQL — review popup then Final Import."""
        upload_repo = ExceptionalStampUploadRepository()
        upload_repo.ensure_schema()
        # Skip ONLY if already in ExceptionalStampImport (Final Import table).
        # Upload history alone must NOT hide rows from the review grid.
        imported_map = upload_repo.imported_certificate_map()
        imported_numbers = set(imported_map)

        parsed = cls.parse_shcil_csv(file_bytes, file_name=file_name)
        previously_uploaded_rows, new_unique_rows = cls._split_previous_uploads(
            parsed["csv_unique_rows"],
            imported_map=imported_map,
        )

        # Correct already-imported dates from Generated On (fixes old report-period dates).
        upload_repo.update_imported_generated_dates(parsed["csv_unique_rows"])

        duplicate_rows = [
            row
            for row in parsed["duplicate_rows"]
            if row.get("certificate_number") not in imported_numbers
        ]

        date_from = (
            date.fromisoformat(parsed["date_from"]) if parsed.get("date_from") else None
        )
        date_to = date.fromisoformat(parsed["date_to"]) if parsed.get("date_to") else None

        # Date column = per-row "Generated On" (do NOT use report From Date for all rows).
        for row in new_unique_rows:
            generated = (row.get("generated_on") or row.get("report_date") or "").strip()
            row["generated_on"] = generated
            row["report_date"] = generated

        # Cards are permanent: Imported Certificates ∩ / − JTCS (not just this upload).
        imported_rows, matched, csv_only, db_only_rows, db_rows = cls._permanent_board(
            upload_repo
        )

        review_rows = [
            {
                "certificate_number": row["certificate_number"],
                "stamp_duty_amount": row["stamp_duty_amount"],
                "stamp_duty_amount_raw": row.get("stamp_duty_amount_raw") or "",
                "stamp_duty_type": row.get("stamp_duty_type") or "",
                "paid_by": row.get("paid_by") or "",
                "certificate_status": row.get("certificate_status") or "",
                "generated_on": row.get("generated_on") or row.get("report_date") or "",
                "generated_on_raw": row.get("generated_on_raw") or "",
                "report_date": row.get("generated_on") or row.get("report_date") or "",
            }
            for row in new_unique_rows
        ]

        return {
            **parsed,
            "duplicate_rows": duplicate_rows,
            "duplicate_count": len(duplicate_rows),
            "batch_id": None,
            "saved": False,
            "review_rows": review_rows,
            "summary": {
                "csv_total_rows": parsed["csv_count"],
                "csv_unique_rows": parsed["csv_unique_count"],
                "csv_new_rows": len(new_unique_rows),
                "previously_uploaded": len(previously_uploaded_rows),
                "registered_new": 0,
                "not_saved": len(new_unique_rows),
                "db_rows": len(db_rows),
                "matched": len(matched),
                "csv_only": len(csv_only),
                "db_only": len(db_only_rows),
                "duplicates_in_csv": len(duplicate_rows),
                "date_from": parsed.get("date_from"),
                "date_to": parsed.get("date_to"),
                "imported_count": len(imported_rows),
            },
            "previously_uploaded_rows": sorted(
                previously_uploaded_rows,
                key=lambda row: row["certificate_number"],
            ),
            "imported_rows": imported_rows,
            "matched_rows": matched,
            "csv_only_rows": csv_only,
            "db_only_rows": db_only_rows,
        }

    @classmethod
    def final_import(
        cls,
        rows: list[dict],
        *,
        file_name: str = "",
        date_from: date | None = None,
        date_to: date | None = None,
        imported_by: str = "System",
    ) -> dict:
        """Save reviewed rows to ExceptionalStampImport + upload history."""
        upload_repo = ExceptionalStampUploadRepository()
        upload_repo.ensure_schema()

        if not rows:
            raise ValueError("No rows to import.")

        cleaned: list[dict] = []
        seen: set[str] = set()
        for raw in rows:
            cert = cls._normalize_certificate(raw.get("certificate_number"))
            if not cert or not cert.startswith("IN-"):
                continue
            if cert in seen:
                continue
            seen.add(cert)
            # Prefer original CSV cell text so "Rs.100" / "Rs.100.00" never become 10000.
            amount_raw = str(raw.get("stamp_duty_amount_raw") or "").strip()
            amount_edited = raw.get("stamp_duty_amount")
            if amount_raw:
                parsed_raw = cls._parse_stamp_duty_amount(amount_raw)
                parsed_edited = cls._parse_stamp_duty_amount(amount_edited)
                # Guard: old bug stored 100.00 as 10000 — prefer CSV raw parse.
                if parsed_edited in {parsed_raw, parsed_raw * 100, 0}:
                    stamp_amount = parsed_raw
                else:
                    stamp_amount = parsed_edited
            else:
                stamp_amount = cls._parse_stamp_duty_amount(amount_edited)

            generated_source = (
                raw.get("generated_on_raw")
                or raw.get("generated_on")
                or raw.get("report_date")
                or ""
            )
            generated_on = cls._parse_generated_on(generated_source)
            cleaned.append(
                {
                    "certificate_number": cert,
                    "stamp_duty_amount": stamp_amount,
                    "stamp_duty_amount_raw": amount_raw
                    or str(amount_edited or "").strip(),
                    "stamp_duty_type": (raw.get("stamp_duty_type") or "").strip(),
                    "paid_by": (raw.get("paid_by") or "").strip(),
                    "certificate_status": (raw.get("certificate_status") or "").strip(),
                    "generated_on": generated_on,
                    "generated_on_raw": str(
                        raw.get("generated_on_raw") or generated_source or ""
                    ).strip(),
                    "report_date": generated_on,
                }
            )

        if not cleaned:
            raise ValueError("No valid certificate rows to import.")

        imported_map = upload_repo.imported_certificate_map()
        previously_uploaded_rows, new_unique_rows = cls._split_previous_uploads(
            cleaned,
            imported_map=imported_map,
        )

        batch = upload_repo.create_batch(
            file_name=file_name or "Final Import",
            report_date_from=date_from,
            report_date_to=date_to,
            uploaded_by=imported_by,
            total_rows=len(cleaned),
            new_rows=len(new_unique_rows),
            skipped_rows=len(previously_uploaded_rows),
        )

        registered_history = upload_repo.register_new_uploads(
            new_unique_rows,
            batch=batch,
            file_name=file_name or "Final Import",
            uploaded_by=imported_by,
            report_date_from=date_from,
            report_date_to=date_to,
        )
        registered_import = upload_repo.register_final_imports(
            new_unique_rows,
            batch=batch,
            file_name=file_name or "Final Import",
            imported_by=imported_by,
            report_date_from=date_from,
            report_date_to=date_to,
        )
        if previously_uploaded_rows:
            upload_repo.touch_seen(
                [row["certificate_number"] for row in previously_uploaded_rows],
                file_name=file_name or "Final Import",
                report_date_from=date_from,
                report_date_to=date_to,
            )

        # Permanent view: Imported Certificates vs all JTCS stamp activity.
        imported_rows, matched, csv_only, db_only_rows, db_rows = cls._permanent_board(
            upload_repo
        )

        return {
            "file_name": file_name or "Final Import",
            "batch_id": batch.BatchID,
            "saved": True,
            "summary": {
                "csv_total_rows": len(imported_rows),
                "csv_unique_rows": len(imported_rows),
                "csv_new_rows": len(new_unique_rows),
                "previously_uploaded": len(previously_uploaded_rows),
                "registered_new": registered_import,
                "registered_history": registered_history,
                "not_saved": 0,
                "db_rows": len(db_rows),
                "matched": len(matched),
                "csv_only": len(csv_only),
                "db_only": len(db_only_rows),
                "duplicates_in_csv": 0,
                "date_from": date_from.isoformat() if date_from else None,
                "date_to": date_to.isoformat() if date_to else None,
                "imported_count": len(imported_rows),
            },
            "previously_uploaded_rows": sorted(
                previously_uploaded_rows,
                key=lambda row: row["certificate_number"],
            ),
            "imported_rows": imported_rows,
            "matched_rows": matched,
            "csv_only_rows": csv_only,
            "db_only_rows": db_only_rows,
            "duplicate_rows": [],
            "review_rows": [],
        }
