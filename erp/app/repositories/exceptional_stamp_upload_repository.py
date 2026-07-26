from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.exceptional_stamp_upload import (
    ExceptionalStampImport,
    ExceptionalStampUploadBatch,
    ExceptionalStampUploadCertificate,
)


class ExceptionalStampUploadRepository:
    def __init__(self, session: Session | None = None):
        self.session = session or db.session
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        self.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.ExceptionalStampUploadBatch', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.ExceptionalStampUploadBatch (
                        BatchID             INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
                        SourceFileName      NVARCHAR(260) NULL,
                        ReportDateFrom      DATE NULL,
                        ReportDateTo        DATE NULL,
                        UploadedBy          NVARCHAR(150) NULL,
                        UploadedDate        DATETIME2 NOT NULL
                            CONSTRAINT DF_ExceptionalStampUploadBatch_UploadedDate DEFAULT (SYSUTCDATETIME()),
                        TotalRows           INT NOT NULL
                            CONSTRAINT DF_ExceptionalStampUploadBatch_TotalRows DEFAULT (0),
                        NewRows             INT NOT NULL
                            CONSTRAINT DF_ExceptionalStampUploadBatch_NewRows DEFAULT (0),
                        SkippedRows         INT NOT NULL
                            CONSTRAINT DF_ExceptionalStampUploadBatch_SkippedRows DEFAULT (0)
                    );
                END;

                IF OBJECT_ID(N'dbo.ExceptionalStampUploadCertificate', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.ExceptionalStampUploadCertificate (
                        UploadID            INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
                        BatchID             INT NULL,
                        CertificateNumber   NVARCHAR(100) NOT NULL,
                        StampDutyAmount     INT NOT NULL
                            CONSTRAINT DF_ExceptionalStampUploadCertificate_StampDutyAmount DEFAULT (0),
                        StampDutyType       NVARCHAR(300) NULL,
                        PaidBy              NVARCHAR(300) NULL,
                        SourceFileName      NVARCHAR(260) NULL,
                        ReportDateFrom      DATE NULL,
                        ReportDateTo        DATE NULL,
                        UploadedBy          NVARCHAR(150) NULL,
                        UploadedDate        DATETIME2 NOT NULL
                            CONSTRAINT DF_ExceptionalStampUploadCertificate_UploadedDate DEFAULT (SYSUTCDATETIME()),
                        LastSeenDate        DATETIME2 NULL,
                        CONSTRAINT UX_ExceptionalStampUploadCertificate_CertificateNumber
                            UNIQUE (CertificateNumber),
                        CONSTRAINT FK_ExceptionalStampUploadCertificate_Batch
                            FOREIGN KEY (BatchID) REFERENCES dbo.ExceptionalStampUploadBatch(BatchID)
                    );
                END;

                IF COL_LENGTH(N'dbo.ExceptionalStampUploadCertificate', N'BatchID') IS NULL
                    ALTER TABLE dbo.ExceptionalStampUploadCertificate ADD BatchID INT NULL;
                IF COL_LENGTH(N'dbo.ExceptionalStampUploadCertificate', N'ReportDateFrom') IS NULL
                    ALTER TABLE dbo.ExceptionalStampUploadCertificate ADD ReportDateFrom DATE NULL;
                IF COL_LENGTH(N'dbo.ExceptionalStampUploadCertificate', N'ReportDateTo') IS NULL
                    ALTER TABLE dbo.ExceptionalStampUploadCertificate ADD ReportDateTo DATE NULL;
                IF COL_LENGTH(N'dbo.ExceptionalStampUploadCertificate', N'StampDutyType') IS NULL
                    ALTER TABLE dbo.ExceptionalStampUploadCertificate ADD StampDutyType NVARCHAR(300) NULL;
                IF COL_LENGTH(N'dbo.ExceptionalStampUploadCertificate', N'PaidBy') IS NULL
                    ALTER TABLE dbo.ExceptionalStampUploadCertificate ADD PaidBy NVARCHAR(300) NULL;

                IF OBJECT_ID(N'dbo.ExceptionalStampImport', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.ExceptionalStampImport (
                        ImportID            INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
                        BatchID             INT NULL,
                        CertificateNumber   NVARCHAR(100) NOT NULL,
                        StampDutyAmount     INT NOT NULL
                            CONSTRAINT DF_ExceptionalStampImport_StampDutyAmount DEFAULT (0),
                        StampDutyType       NVARCHAR(300) NULL,
                        PaidBy              NVARCHAR(300) NULL,
                        CertificateStatus   NVARCHAR(300) NULL,
                        SourceFileName      NVARCHAR(260) NULL,
                        ReportDateFrom      DATE NULL,
                        ReportDateTo        DATE NULL,
                        ImportedBy          NVARCHAR(150) NULL,
                        ImportedDate        DATETIME2 NOT NULL
                            CONSTRAINT DF_ExceptionalStampImport_ImportedDate DEFAULT (SYSUTCDATETIME()),
                        CONSTRAINT UX_ExceptionalStampImport_CertificateNumber
                            UNIQUE (CertificateNumber)
                    );
                END;

                IF COL_LENGTH(N'dbo.ExceptionalStampImport', N'CertificateStatus') IS NULL
                    ALTER TABLE dbo.ExceptionalStampImport ADD CertificateStatus NVARCHAR(300) NULL;
                IF COL_LENGTH(N'dbo.ExceptionalStampImport', N'BatchID') IS NULL
                    ALTER TABLE dbo.ExceptionalStampImport ADD BatchID INT NULL;
                IF COL_LENGTH(N'dbo.ExceptionalStampImport', N'StampDutyType') IS NULL
                    ALTER TABLE dbo.ExceptionalStampImport ADD StampDutyType NVARCHAR(300) NULL;
                IF COL_LENGTH(N'dbo.ExceptionalStampImport', N'PaidBy') IS NULL
                    ALTER TABLE dbo.ExceptionalStampImport ADD PaidBy NVARCHAR(300) NULL;
                IF COL_LENGTH(N'dbo.ExceptionalStampImport', N'SourceFileName') IS NULL
                    ALTER TABLE dbo.ExceptionalStampImport ADD SourceFileName NVARCHAR(260) NULL;
                IF COL_LENGTH(N'dbo.ExceptionalStampImport', N'ReportDateFrom') IS NULL
                    ALTER TABLE dbo.ExceptionalStampImport ADD ReportDateFrom DATE NULL;
                IF COL_LENGTH(N'dbo.ExceptionalStampImport', N'ReportDateTo') IS NULL
                    ALTER TABLE dbo.ExceptionalStampImport ADD ReportDateTo DATE NULL;
                IF COL_LENGTH(N'dbo.ExceptionalStampImport', N'ImportedBy') IS NULL
                    ALTER TABLE dbo.ExceptionalStampImport ADD ImportedBy NVARCHAR(150) NULL;
                """
            )
        )
        self._schema_ready = True

    def known_certificate_map(self) -> dict[str, ExceptionalStampUploadCertificate]:
        self.ensure_schema()
        rows = self.session.scalars(select(ExceptionalStampUploadCertificate)).all()
        return {
            (row.CertificateNumber or "").strip().upper(): row
            for row in rows
            if (row.CertificateNumber or "").strip()
        }

    def imported_certificate_map(self) -> dict[str, ExceptionalStampImport]:
        """Certificates already final-imported (source of truth for skip)."""
        self.ensure_schema()
        rows = self.session.scalars(select(ExceptionalStampImport)).all()
        return {
            (row.CertificateNumber or "").strip().upper(): row
            for row in rows
            if (row.CertificateNumber or "").strip()
        }

    def update_imported_generated_dates(self, rows: list[dict]) -> int:
        """Backfill ReportDateFrom/To from per-row Generated On for already-imported certs."""
        self.ensure_schema()
        if not rows:
            return 0
        known = self.imported_certificate_map()
        updated = 0
        for row in rows:
            cert = (row.get("certificate_number") or "").strip().upper()
            existing = known.get(cert)
            if existing is None:
                continue
            generated_raw = (row.get("generated_on") or row.get("report_date") or "").strip()
            if not generated_raw:
                continue
            try:
                row_date = date.fromisoformat(generated_raw[:10])
            except ValueError:
                continue
            if existing.ReportDateFrom != row_date or existing.ReportDateTo != row_date:
                existing.ReportDateFrom = row_date
                existing.ReportDateTo = row_date
                updated += 1
        if updated:
            self.session.flush()
        return updated

    def known_or_imported_certificate_numbers(self) -> set[str]:
        """Union of history + final import — used to skip re-uploads."""
        known = set(self.known_certificate_map())
        known.update(self.imported_certificate_map())
        return known

    def create_batch(
        self,
        *,
        file_name: str,
        report_date_from: date | None,
        report_date_to: date | None,
        uploaded_by: str,
        total_rows: int,
        new_rows: int,
        skipped_rows: int,
    ) -> ExceptionalStampUploadBatch:
        self.ensure_schema()
        batch = ExceptionalStampUploadBatch(
            SourceFileName=(file_name or "").strip() or None,
            ReportDateFrom=report_date_from,
            ReportDateTo=report_date_to,
            UploadedBy=(uploaded_by or "").strip() or None,
            UploadedDate=datetime.utcnow(),
            TotalRows=int(total_rows or 0),
            NewRows=int(new_rows or 0),
            SkippedRows=int(skipped_rows or 0),
        )
        self.session.add(batch)
        self.session.flush()
        return batch

    def register_new_uploads(
        self,
        rows: list[dict],
        *,
        batch: ExceptionalStampUploadBatch,
        file_name: str,
        uploaded_by: str,
        report_date_from: date | None,
        report_date_to: date | None,
    ) -> int:
        self.ensure_schema()
        if not rows:
            return 0
        known = self.known_certificate_map()
        created = 0
        now = datetime.utcnow()
        for row in rows:
            cert = (row.get("certificate_number") or "").strip().upper()
            if not cert or cert in known:
                continue
            # Prefer per-certificate Generated On; fall back to batch report dates.
            row_date = None
            generated_raw = (row.get("generated_on") or row.get("report_date") or "").strip()
            if generated_raw:
                try:
                    row_date = date.fromisoformat(generated_raw[:10])
                except ValueError:
                    row_date = None
            upload_row = ExceptionalStampUploadCertificate(
                BatchID=batch.BatchID,
                CertificateNumber=cert,
                StampDutyAmount=int(row.get("stamp_duty_amount") or 0),
                StampDutyType=(row.get("stamp_duty_type") or "").strip() or None,
                PaidBy=(row.get("paid_by") or "").strip() or None,
                SourceFileName=(file_name or "").strip() or None,
                ReportDateFrom=row_date or report_date_from,
                ReportDateTo=row_date or report_date_to,
                UploadedBy=(uploaded_by or "").strip() or None,
                UploadedDate=now,
                LastSeenDate=None,
            )
            self.session.add(upload_row)
            known[cert] = upload_row
            created += 1
        if created:
            self.session.flush()
        return created

    def register_final_imports(
        self,
        rows: list[dict],
        *,
        batch: ExceptionalStampUploadBatch,
        file_name: str,
        imported_by: str,
        report_date_from: date | None,
        report_date_to: date | None,
    ) -> int:
        """Insert reviewed rows into ExceptionalStampImport (skip already imported)."""
        self.ensure_schema()
        if not rows:
            return 0
        known = self.imported_certificate_map()
        created = 0
        now = datetime.utcnow()
        for row in rows:
            cert = (row.get("certificate_number") or "").strip().upper()
            if not cert or cert in known:
                continue
            # Prefer per-certificate Generated On; fall back to batch report dates.
            row_date = None
            generated_raw = (row.get("generated_on") or row.get("report_date") or "").strip()
            if generated_raw:
                try:
                    row_date = date.fromisoformat(generated_raw[:10])
                except ValueError:
                    row_date = None
            import_row = ExceptionalStampImport(
                BatchID=batch.BatchID,
                CertificateNumber=cert,
                StampDutyAmount=int(row.get("stamp_duty_amount") or 0),
                StampDutyType=(row.get("stamp_duty_type") or "").strip() or None,
                PaidBy=(row.get("paid_by") or "").strip() or None,
                CertificateStatus=(row.get("certificate_status") or "").strip() or None,
                SourceFileName=(file_name or "").strip() or None,
                ReportDateFrom=row_date or report_date_from,
                ReportDateTo=row_date or report_date_to,
                ImportedBy=(imported_by or "").strip() or None,
                ImportedDate=now,
            )
            self.session.add(import_row)
            known[cert] = import_row
            created += 1
        if created:
            self.session.flush()
        return created

    def touch_seen(
        self,
        certificates: list[str],
        *,
        file_name: str,
        report_date_from: date | None,
        report_date_to: date | None,
    ) -> None:
        self.ensure_schema()
        if not certificates:
            return
        known = self.known_certificate_map()
        now = datetime.utcnow()
        for cert_raw in certificates:
            cert = (cert_raw or "").strip().upper()
            row = known.get(cert)
            if row is None:
                continue
            row.LastSeenDate = now
            if file_name:
                row.SourceFileName = file_name
            if report_date_from:
                row.ReportDateFrom = report_date_from
            if report_date_to:
                row.ReportDateTo = report_date_to
        self.session.flush()

    @staticmethod
    def _cert_row_dict(row: ExceptionalStampUploadCertificate) -> dict:
        return {
            "certificate_number": (row.CertificateNumber or "").strip().upper(),
            "stamp_duty_amount": int(row.StampDutyAmount or 0),
            "stamp_duty_type": (row.StampDutyType or "").strip(),
            "paid_by": (row.PaidBy or "").strip(),
            "uploaded_date": row.UploadedDate.isoformat() if row.UploadedDate else "",
            "report_date_from": row.ReportDateFrom.isoformat() if row.ReportDateFrom else "",
            "report_date_to": row.ReportDateTo.isoformat() if row.ReportDateTo else "",
            "source_file_name": (row.SourceFileName or "").strip(),
            "uploaded_by": (row.UploadedBy or "").strip(),
        }

    @staticmethod
    def _import_row_dict(row: ExceptionalStampImport) -> dict:
        report_date = ""
        if row.ReportDateFrom:
            report_date = row.ReportDateFrom.isoformat()
        elif row.ImportedDate:
            report_date = row.ImportedDate.date().isoformat()
        return {
            "certificate_number": (row.CertificateNumber or "").strip().upper(),
            "stamp_duty_amount": int(row.StampDutyAmount or 0),
            "stamp_duty_type": (row.StampDutyType or "").strip(),
            "paid_by": (row.PaidBy or "").strip(),
            "certificate_status": (row.CertificateStatus or "").strip(),
            "report_date": report_date,
            "imported_date": row.ImportedDate.isoformat() if row.ImportedDate else "",
            "report_date_from": row.ReportDateFrom.isoformat() if row.ReportDateFrom else "",
            "report_date_to": row.ReportDateTo.isoformat() if row.ReportDateTo else "",
            "source_file_name": (row.SourceFileName or "").strip(),
            "imported_by": (row.ImportedBy or "").strip(),
        }

    def list_all_imported_rows(self) -> list[dict]:
        """All Final Import rows — permanent source for page reload / skip."""
        self.ensure_schema()
        rows = self.session.scalars(
            select(ExceptionalStampImport).order_by(
                ExceptionalStampImport.ImportedDate.desc(),
                ExceptionalStampImport.CertificateNumber,
            )
        ).all()
        return [self._import_row_dict(row) for row in rows]

    def list_imported_rows_for_period(
        self,
        *,
        date_from: date | None,
        date_to: date | None,
    ) -> list[dict]:
        """Imported certificates; if no dates given, returns all."""
        if date_from is None and date_to is None:
            return self.list_all_imported_rows()
        self.ensure_schema()
        rows = self.session.scalars(
            select(ExceptionalStampImport).order_by(ExceptionalStampImport.CertificateNumber)
        ).all()
        result: list[dict] = []
        for row in rows:
            report_from = row.ReportDateFrom
            report_to = row.ReportDateTo
            if date_from and date_to and report_from and report_to:
                if report_from > date_to or report_to < date_from:
                    continue
            result.append(self._import_row_dict(row))
        return result

    def list_upload_groups(self) -> list[dict]:
        self.ensure_schema()
        batches = self.session.scalars(
            select(ExceptionalStampUploadBatch).order_by(
                ExceptionalStampUploadBatch.UploadedDate.desc(),
                ExceptionalStampUploadBatch.BatchID.desc(),
            )
        ).all()
        groups: list[dict] = []
        for batch in batches:
            certs = self.session.scalars(
                select(ExceptionalStampUploadCertificate)
                .where(ExceptionalStampUploadCertificate.BatchID == batch.BatchID)
                .order_by(ExceptionalStampUploadCertificate.CertificateNumber)
            ).all()
            groups.append(
                {
                    "batch_id": batch.BatchID,
                    "source_file_name": (batch.SourceFileName or "").strip(),
                    "report_date_from": batch.ReportDateFrom.isoformat() if batch.ReportDateFrom else "",
                    "report_date_to": batch.ReportDateTo.isoformat() if batch.ReportDateTo else "",
                    "uploaded_date": batch.UploadedDate.isoformat() if batch.UploadedDate else "",
                    "uploaded_by": (batch.UploadedBy or "").strip(),
                    "total_rows": int(batch.TotalRows or 0),
                    "new_rows": int(batch.NewRows or 0),
                    "skipped_rows": int(batch.SkippedRows or 0),
                    "certificates": [self._cert_row_dict(cert) for cert in certs],
                }
            )

        orphan_certs = self.session.scalars(
            select(ExceptionalStampUploadCertificate)
            .where(ExceptionalStampUploadCertificate.BatchID.is_(None))
            .order_by(
                ExceptionalStampUploadCertificate.UploadedDate.desc(),
                ExceptionalStampUploadCertificate.CertificateNumber,
            )
        ).all()
        if orphan_certs:
            groups.append(
                {
                    "batch_id": 0,
                    "source_file_name": "Earlier uploads",
                    "report_date_from": "",
                    "report_date_to": "",
                    "uploaded_date": orphan_certs[0].UploadedDate.isoformat()
                    if orphan_certs[0].UploadedDate
                    else "",
                    "uploaded_by": "",
                    "total_rows": len(orphan_certs),
                    "new_rows": len(orphan_certs),
                    "skipped_rows": 0,
                    "certificates": [self._cert_row_dict(cert) for cert in orphan_certs],
                }
            )
        return groups

    def uploaded_certificate_numbers_for_date(self, txn_date: date) -> set[str]:
        self.ensure_schema()
        uploaded: set[str] = set()

        history_rows = self.session.scalars(select(ExceptionalStampUploadCertificate)).all()
        for row in history_rows:
            cert = (row.CertificateNumber or "").strip().upper()
            if not cert:
                continue
            report_from = row.ReportDateFrom
            report_to = row.ReportDateTo
            if report_from and report_to:
                if report_from <= txn_date <= report_to:
                    uploaded.add(cert)
            else:
                uploaded.add(cert)

        import_rows = self.session.scalars(select(ExceptionalStampImport)).all()
        for row in import_rows:
            cert = (row.CertificateNumber or "").strip().upper()
            if not cert:
                continue
            report_from = row.ReportDateFrom
            report_to = row.ReportDateTo
            if report_from and report_to:
                if report_from <= txn_date <= report_to:
                    uploaded.add(cert)
            else:
                uploaded.add(cert)
        return uploaded

    def uploaded_certificate_numbers_for_period(
        self,
        *,
        date_from: date | None,
        date_to: date | None,
    ) -> set[str]:
        self.ensure_schema()
        if date_from is None and date_to is None:
            numbers = set(self.known_or_imported_certificate_numbers())
            return numbers

        if date_from is None:
            date_from = date_to
        if date_to is None:
            date_to = date_from
        if date_from is None or date_to is None:
            return set()

        uploaded: set[str] = set()
        for row in self.session.scalars(select(ExceptionalStampUploadCertificate)).all():
            cert = (row.CertificateNumber or "").strip().upper()
            if not cert:
                continue
            report_from = row.ReportDateFrom
            report_to = row.ReportDateTo
            if report_from and report_to:
                if report_from <= date_to and report_to >= date_from:
                    uploaded.add(cert)
            else:
                uploaded.add(cert)
        for row in self.session.scalars(select(ExceptionalStampImport)).all():
            cert = (row.CertificateNumber or "").strip().upper()
            if not cert:
                continue
            report_from = row.ReportDateFrom
            report_to = row.ReportDateTo
            if report_from and report_to:
                if report_from <= date_to and report_to >= date_from:
                    uploaded.add(cert)
            else:
                uploaded.add(cert)
        return uploaded
