from __future__ import annotations

from datetime import date

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.gst_billing import GstInvoice, GstInvoiceLine


class GstInvoiceRepository:
    def __init__(self, session: Session | None = None):
        self.session = session or db.session
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        # ItemMaster may be created by its own repo; invoice tables here.
        self.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.GstInvoice', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.GstInvoice (
                        InvoiceID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
                        InvoiceNo NVARCHAR(40) NOT NULL,
                        InvoiceDate DATE NOT NULL,
                        CustomerID INT NULL,
                        CustomerName NVARCHAR(200) NOT NULL,
                        ContactPerson NVARCHAR(150) NULL,
                        BillingAddress NVARCHAR(500) NULL,
                        CustomerGSTIN NVARCHAR(20) NULL,
                        ContactMobile NVARCHAR(20) NULL,
                        ContactEmail NVARCHAR(150) NULL,
                        PlaceOfSupply NVARCHAR(100) NULL,
                        PlaceOfSupplyCode NVARCHAR(5) NULL,
                        ReverseCharge BIT NOT NULL CONSTRAINT DF_GstInvoice_RCM DEFAULT (0),
                        TaxType NVARCHAR(10) NOT NULL CONSTRAINT DF_GstInvoice_TaxType DEFAULT (N'IGST'),
                        ListPrice DECIMAL(18, 2) NOT NULL CONSTRAINT DF_GstInvoice_ListPrice DEFAULT (0),
                        DiscountAmount DECIMAL(18, 2) NOT NULL CONSTRAINT DF_GstInvoice_Discount DEFAULT (0),
                        TaxableValue DECIMAL(18, 2) NOT NULL CONSTRAINT DF_GstInvoice_Taxable DEFAULT (0),
                        CgstRate DECIMAL(5, 2) NOT NULL CONSTRAINT DF_GstInvoice_CgstRate DEFAULT (0),
                        CgstAmount DECIMAL(18, 2) NOT NULL CONSTRAINT DF_GstInvoice_CgstAmt DEFAULT (0),
                        SgstRate DECIMAL(5, 2) NOT NULL CONSTRAINT DF_GstInvoice_SgstRate DEFAULT (0),
                        SgstAmount DECIMAL(18, 2) NOT NULL CONSTRAINT DF_GstInvoice_SgstAmt DEFAULT (0),
                        IgstRate DECIMAL(5, 2) NOT NULL CONSTRAINT DF_GstInvoice_IgstRate DEFAULT (0),
                        IgstAmount DECIMAL(18, 2) NOT NULL CONSTRAINT DF_GstInvoice_IgstAmt DEFAULT (0),
                        InvoiceValue DECIMAL(18, 2) NOT NULL CONSTRAINT DF_GstInvoice_Value DEFAULT (0),
                        AmountInWords NVARCHAR(500) NULL,
                        Notes NVARCHAR(500) NULL,
                        CreatedBy NVARCHAR(100) NULL,
                        CreatedAt DATETIME2 NOT NULL CONSTRAINT DF_GstInvoice_CreatedAt DEFAULT (SYSUTCDATETIME()),
                        UpdatedAt DATETIME2 NULL,
                        CONSTRAINT UX_GstInvoice_No UNIQUE (InvoiceNo)
                    );
                END
                """
            )
        )
        self.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.GstInvoiceLine', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.GstInvoiceLine (
                        LineID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
                        InvoiceID INT NOT NULL,
                        SrNo INT NOT NULL,
                        ItemID INT NULL,
                        Particulars NVARCHAR(300) NOT NULL,
                        HsnSac NVARCHAR(20) NULL,
                        Unit NVARCHAR(30) NULL,
                        Qty DECIMAL(18, 3) NOT NULL CONSTRAINT DF_GstInvoiceLine_Qty DEFAULT (1),
                        Rate DECIMAL(18, 2) NOT NULL CONSTRAINT DF_GstInvoiceLine_Rate DEFAULT (0),
                        DiscountAmount DECIMAL(18, 2) NOT NULL CONSTRAINT DF_GstInvoiceLine_Discount DEFAULT (0),
                        TaxableValue DECIMAL(18, 2) NOT NULL CONSTRAINT DF_GstInvoiceLine_Taxable DEFAULT (0),
                        GstRatePercent DECIMAL(5, 2) NOT NULL CONSTRAINT DF_GstInvoiceLine_GstRate DEFAULT (0),
                        CONSTRAINT FK_GstInvoiceLine_Invoice FOREIGN KEY (InvoiceID)
                            REFERENCES dbo.GstInvoice (InvoiceID) ON DELETE CASCADE
                    );
                    CREATE INDEX IX_GstInvoiceLine_InvoiceID ON dbo.GstInvoiceLine (InvoiceID);
                END
                """
            )
        )
        for col, ddl in (
            ("PaymentBankAccountID", "INT NULL"),
            ("PayBankName", "NVARCHAR(150) NULL"),
            ("PayAccountNumber", "NVARCHAR(50) NULL"),
            ("PayIFSC", "NVARCHAR(20) NULL"),
            ("PayBranch", "NVARCHAR(150) NULL"),
            ("PayAccountHolder", "NVARCHAR(150) NULL"),
            ("PayAccountType", "NVARCHAR(20) NULL"),
            ("PayUpiId", "NVARCHAR(100) NULL"),
            ("InvoiceKind", "NVARCHAR(20) NOT NULL CONSTRAINT DF_GstInvoice_InvoiceKind DEFAULT (N'NON_GST')"),
            ("VoucherType", "NVARCHAR(20) NOT NULL CONSTRAINT DF_GstInvoice_VoucherType DEFAULT (N'SALE')"),
            ("PaymentDate", "DATE NULL"),
            ("AmountPaid", "DECIMAL(18,2) NULL"),
        ):
            self.session.execute(
                text(
                    f"""
                    IF COL_LENGTH(N'dbo.GstInvoice', N'{col}') IS NULL
                        ALTER TABLE dbo.GstInvoice ADD {col} {ddl};
                    """
                )
            )
            self.session.commit()
        for col, ddl in (
            ("TaxPeriod", "NVARCHAR(20) NULL"),
            ("Quarter", "NVARCHAR(40) NULL"),
            ("Month", "NVARCHAR(20) NULL"),
        ):
            self.session.execute(
                text(
                    f"""
                    IF COL_LENGTH(N'dbo.GstInvoiceLine', N'{col}') IS NULL
                        ALTER TABLE dbo.GstInvoiceLine ADD {col} {ddl};
                    """
                )
            )
            self.session.commit()
        self._schema_ready = True

    def list_all(
        self,
        *,
        search: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        voucher_type: str | None = None,
    ) -> list[GstInvoice]:
        self.ensure_schema()
        stmt = select(GstInvoice)
        if voucher_type:
            vt = voucher_type.strip().upper()
            if vt in {"SALE", "PURCHASE"}:
                stmt = stmt.where(GstInvoice.VoucherType == vt)
        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(
                (GstInvoice.InvoiceNo.like(term))
                | (GstInvoice.CustomerName.like(term))
                | (GstInvoice.CustomerGSTIN.like(term))
            )
        if date_from:
            stmt = stmt.where(GstInvoice.InvoiceDate >= date_from)
        if date_to:
            stmt = stmt.where(GstInvoice.InvoiceDate <= date_to)
        stmt = stmt.order_by(GstInvoice.InvoiceDate.desc(), GstInvoice.InvoiceID.desc())
        return list(self.session.scalars(stmt).all())

    def get_by_id(self, invoice_id: int) -> GstInvoice | None:
        self.ensure_schema()
        return self.session.get(GstInvoice, invoice_id)

    def list_lines(self, invoice_id: int) -> list[GstInvoiceLine]:
        self.ensure_schema()
        stmt = (
            select(GstInvoiceLine)
            .where(GstInvoiceLine.InvoiceID == invoice_id)
            .order_by(GstInvoiceLine.SrNo.asc())
        )
        return list(self.session.scalars(stmt).all())

    def next_sequence(self, prefix: str) -> int:
        self.ensure_schema()
        like = f"{prefix}%"
        row = self.session.execute(
            text(
                """
                SELECT MAX(InvoiceNo) AS MaxNo
                FROM dbo.GstInvoice
                WHERE InvoiceNo LIKE :like
                """
            ),
            {"like": like},
        ).mappings().first()
        max_no = (row["MaxNo"] if row else None) or ""
        if not max_no:
            return 1
        tail = max_no.rsplit("/", 1)[-1]
        try:
            return int(tail) + 1
        except ValueError:
            return 1

    def list_ids(self) -> list[int]:
        """Invoice IDs oldest → newest (Top=first, Bottom=last)."""
        self.ensure_schema()
        rows = self.session.execute(
            text(
                """
                SELECT InvoiceID
                FROM dbo.GstInvoice
                ORDER BY InvoiceID ASC
                """
            )
        ).scalars().all()
        return [int(r) for r in rows]

    def create(self, header: dict, lines: list[dict]) -> GstInvoice:
        self.ensure_schema()
        inv = GstInvoice(**header)
        self.session.add(inv)
        self.session.flush()
        for line in lines:
            self.session.add(GstInvoiceLine(InvoiceID=inv.InvoiceID, **line))
        self.session.flush()
        return inv

    def update(self, invoice: GstInvoice, header: dict, lines: list[dict]) -> GstInvoice:
        self.ensure_schema()
        for key, value in header.items():
            if key in {"CreatedAt", "CreatedBy", "InvoiceNo"}:
                continue
            setattr(invoice, key, value)
        invoice.UpdatedAt = header.get("UpdatedAt")
        # Replace lines
        existing = self.list_lines(invoice.InvoiceID)
        for row in existing:
            self.session.delete(row)
        self.session.flush()
        for line in lines:
            self.session.add(GstInvoiceLine(InvoiceID=invoice.InvoiceID, **line))
        self.session.flush()
        return invoice

    def delete(self, invoice: GstInvoice) -> None:
        self.session.delete(invoice)
        self.session.flush()
