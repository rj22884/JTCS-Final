"""Income Expense New — grid for moved Income/Expense records."""

from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.others import IncomeExpenseNewDetail, IncomeExpenseNewMaster, WorkMaster
from app.models.transactions import JTCSDailyTransaction, JTCSDailyTransactionPayment, JtcsBankAccountMaster


class IncomeExpenseNewService:
    LEDGER_INCOME = "Income"
    LEDGER_EXPENSE = "Expense"
    LEDGER_KINDS = (LEDGER_INCOME, LEDGER_EXPENSE)

    def ensure_schema(self) -> None:
        """Create destination tables if move.bat has not run yet."""
        db.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.IncomeExpenseNewMaster', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.IncomeExpenseNewMaster (
                        EntryID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                        SourceEntryID INT NULL,
                        BillNo NVARCHAR(50) NOT NULL,
                        WorkDate DATE NOT NULL,
                        WorkID INT NOT NULL,
                        Amount DECIMAL(18, 2) NOT NULL,
                        CustomerName NVARCHAR(255) NULL,
                        MobileNumber NVARCHAR(15) NULL,
                        Remarks NVARCHAR(500) NULL,
                        CreatedBy NVARCHAR(100) NULL,
                        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_IEN_CreatedDate DEFAULT (SYSUTCDATETIME()),
                        IsActive BIT NOT NULL CONSTRAINT DF_IEN_IsActive DEFAULT (1),
                        CustomerID INT NULL,
                        WorkDone BIT NOT NULL CONSTRAINT DF_IEN_WorkDone DEFAULT (0),
                        TallyBillGenerated BIT NOT NULL CONSTRAINT DF_IEN_TallyBillGenerated DEFAULT (0),
                        TallyBillNo NVARCHAR(50) NULL,
                        TallyBillDate DATE NULL,
                        TallyBillAmount DECIMAL(18, 2) NULL,
                        PaymentReceived BIT NOT NULL CONSTRAINT DF_IEN_PaymentReceived DEFAULT (0),
                        MovedAt DATETIME2 NULL,
                        CONSTRAINT UX_IncomeExpenseNewMaster_BillNo UNIQUE (BillNo)
                    );
                END
                """
            )
        )
        db.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.IncomeExpenseNewDetail', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.IncomeExpenseNewDetail (
                        DetailID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                        EntryID INT NOT NULL,
                        SourceDetailID INT NULL,
                        LineSequence INT NOT NULL,
                        WorkID INT NOT NULL,
                        Amount DECIMAL(18, 2) NOT NULL,
                        WorkTypeID INT NULL,
                        CONSTRAINT FK_IncomeExpenseNewDetail_Entry
                            FOREIGN KEY (EntryID) REFERENCES dbo.IncomeExpenseNewMaster (EntryID),
                        CONSTRAINT UX_IncomeExpenseNewDetail_Entry_Seq UNIQUE (EntryID, LineSequence)
                    );
                END
                """
            )
        )
        db.session.execute(
            text(
                """
                IF COL_LENGTH(N'dbo.IncomeExpenseNewMaster', N'Transferred') IS NOT NULL
                BEGIN
                    DECLARE @df_ien_xfer sysname;
                    DECLARE @sql_ien_xfer nvarchar(400);
                    SELECT @df_ien_xfer = dc.name
                    FROM sys.default_constraints dc
                    INNER JOIN sys.columns c
                        ON c.default_object_id = dc.object_id
                       AND c.object_id = dc.parent_object_id
                    WHERE dc.parent_object_id = OBJECT_ID(N'dbo.IncomeExpenseNewMaster')
                      AND c.name = N'Transferred';
                    IF @df_ien_xfer IS NOT NULL
                    BEGIN
                        SET @sql_ien_xfer = N'ALTER TABLE dbo.IncomeExpenseNewMaster DROP CONSTRAINT '
                            + QUOTENAME(@df_ien_xfer);
                        EXEC sys.sp_executesql @sql_ien_xfer;
                    END
                    ALTER TABLE dbo.IncomeExpenseNewMaster DROP COLUMN Transferred;
                END
                """
            )
        )
        db.session.commit()

    @staticmethod
    def _account_label(bank_name: str | None, account_number: str | None) -> str:
        acct = (account_number or "").strip()
        if acct.upper() in {"CASH", "CASH IN HAND"} or (bank_name or "").strip().upper() == "CASH":
            return "Cash"
        digits = "".join(ch for ch in acct if ch.isdigit())
        if len(digits) >= 4:
            return digits[-4:]
        if acct:
            return acct[-4:] if len(acct) > 4 else acct
        return (bank_name or "").strip() or "—"

    def _account_labels_by_bill(self, bill_nos: list[str]) -> dict[str, str]:
        keys = sorted({(b or "").strip().upper() for b in bill_nos if (b or "").strip()})
        if not keys:
            return {}
        rows = db.session.execute(
            select(
                JTCSDailyTransaction.ReferenceNo,
                JtcsBankAccountMaster.BankName,
                JtcsBankAccountMaster.AccountNumber,
                JTCSDailyTransactionPayment.PaymentMode,
            )
            .outerjoin(
                JTCSDailyTransactionPayment,
                JTCSDailyTransactionPayment.TransactionID == JTCSDailyTransaction.TransactionID,
            )
            .outerjoin(
                JtcsBankAccountMaster,
                JtcsBankAccountMaster.BankAccountID == JTCSDailyTransactionPayment.BankAccountID,
            )
            .where(JTCSDailyTransaction.ReferenceNo.in_(keys))
            .where(JTCSDailyTransaction.Status == "Posted")
        ).all()
        out: dict[str, str] = {}
        for ref, bank_name, account_number, payment_mode in rows:
            key = (ref or "").strip().upper()
            if not key or key in out:
                continue
            mode = (payment_mode or "").strip().upper()
            if mode == "CASH" or (account_number or "").strip().upper() in {"CASH", "CASH IN HAND"}:
                out[key] = "Cash"
            else:
                out[key] = self._account_label(bank_name, account_number)
        return out

    def _category_name(self, row: IncomeExpenseNewMaster) -> str:
        details = list(getattr(row, "detail_lines", None) or [])
        names: list[str] = []
        for detail in sorted(details, key=lambda d: d.LineSequence or 0):
            work = getattr(detail, "work_type", None)
            name = (work.WorkName if work else "") or ""
            if name:
                names.append(name)
        if names:
            return ", ".join(names)
        work = getattr(row, "work_type", None)
        return (work.WorkName if work else "") or ""

    def _entry_dict(self, row: IncomeExpenseNewMaster) -> dict:
        work = getattr(row, "work_type", None)
        ledger_kind = (work.LedgerKind if work else self.LEDGER_INCOME) or self.LEDGER_INCOME
        return {
            "entry_id": row.EntryID,
            "source_entry_id": getattr(row, "SourceEntryID", None),
            "bill_no": row.BillNo,
            "work_date": row.WorkDate.isoformat() if row.WorkDate else "",
            "work_id": row.WorkID,
            "work_name": self._category_name(row),
            "ledger_kind": ledger_kind,
            "amount": str(row.Amount),
            "account_label": "—",
            "customer_name": row.CustomerName or "",
            "mobile_number": row.MobileNumber or "",
            "customer_id": getattr(row, "CustomerID", None),
            "remarks": row.Remarks or "",
            "created_date": row.CreatedDate.isoformat() if row.CreatedDate else "",
            "moved_at": row.MovedAt.isoformat() if getattr(row, "MovedAt", None) else "",
        }

    def list_entries(self, *, ledger_kind: str | None = None) -> list[dict]:
        self.ensure_schema()
        kind = (ledger_kind or "").strip()
        if kind and kind not in self.LEDGER_KINDS:
            kind = ""

        stmt = (
            select(IncomeExpenseNewMaster)
            .options(
                joinedload(IncomeExpenseNewMaster.work_type),
                joinedload(IncomeExpenseNewMaster.detail_lines).joinedload(
                    IncomeExpenseNewDetail.work_type
                ),
            )
            .join(WorkMaster, IncomeExpenseNewMaster.WorkID == WorkMaster.WorkID)
            .where(IncomeExpenseNewMaster.IsActive == True)  # noqa: E712
            .where(WorkMaster.LedgerKind.in_(list(self.LEDGER_KINDS)))
            .order_by(
                IncomeExpenseNewMaster.WorkDate.desc(),
                IncomeExpenseNewMaster.EntryID.desc(),
            )
        )
        if kind:
            stmt = stmt.where(WorkMaster.LedgerKind == kind)

        rows = list(db.session.scalars(stmt).unique().all())
        entries = [self._entry_dict(row) for row in rows]
        account_map = self._account_labels_by_bill(
            [item.get("bill_no") or "" for item in entries]
        )
        for item in entries:
            item["account_label"] = account_map.get(
                (item.get("bill_no") or "").strip().upper(), "—"
            )
        return entries
