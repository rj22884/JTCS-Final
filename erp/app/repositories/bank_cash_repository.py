from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.bank_cash import OthersBankCashTransaction, RdAccountMaster
from app.models.transactions import JtcsBankAccountMaster, JtcsBankTransaction


class RdAccountRepository:
    def __init__(self, session: Session | None = None):
        self.session = session or db.session

    def list_all(self, *, search: str | None = None, active_only: bool = False) -> list[RdAccountMaster]:
        stmt = select(RdAccountMaster).order_by(RdAccountMaster.RdName, RdAccountMaster.RdAccountID)
        if active_only:
            stmt = stmt.where(RdAccountMaster.ActiveStatus == True)  # noqa: E712
        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    RdAccountMaster.RdName.like(term),
                    RdAccountMaster.RdNumber.like(term),
                    RdAccountMaster.BankName.like(term),
                )
            )
        return list(self.session.scalars(stmt).all())

    def get_by_id(self, rd_account_id: int) -> RdAccountMaster | None:
        return self.session.get(RdAccountMaster, rd_account_id)

    def create(self, data: dict) -> RdAccountMaster:
        now = datetime.utcnow()
        data.setdefault("CreatedDate", now)
        data.setdefault("ModifiedDate", now)
        data.setdefault("ActiveStatus", True)
        row = RdAccountMaster(**data)
        self.session.add(row)
        self.session.flush()
        return row

    def update(self, row: RdAccountMaster, data: dict) -> RdAccountMaster:
        preserve = {"RdAccountID", "CreatedDate", "CreatedBy"}
        for key, value in data.items():
            if key not in preserve:
                setattr(row, key, value)
        row.ModifiedDate = datetime.utcnow()
        self.session.flush()
        return row

    def delete(self, row: RdAccountMaster) -> None:
        self.session.delete(row)
        self.session.flush()

    def usage_count(self, bank_account_id: int | None) -> int:
        if not bank_account_id:
            return 0
        return int(
            self.session.scalar(
                select(func.count())
                .select_from(JtcsBankTransaction)
                .where(JtcsBankTransaction.JtcsBankAccountID == bank_account_id)
            )
            or 0
        )


class OthersBankCashRepository:
    def __init__(self, session: Session | None = None):
        self.session = session or db.session
        self._schema_ready = False

    def _column_exists(self, column_name: str) -> bool:
        return bool(
            self.session.execute(
                text(
                    """
                    SELECT 1
                    FROM sys.columns
                    WHERE object_id = OBJECT_ID(N'dbo.OthersBankCashTransaction')
                      AND name = :col
                    """
                ),
                {"col": column_name},
            ).first()
        )

    def _bank_account_nullable(self) -> bool:
        row = self.session.execute(
            text(
                """
                SELECT is_nullable
                FROM sys.columns
                WHERE object_id = OBJECT_ID(N'dbo.OthersBankCashTransaction')
                  AND name = N'CreditBankAccountID'
                """
            )
        ).first()
        return bool(row and str(row[0]).upper() == "YES")

    def ensure_schema(self) -> None:
        """Allow Chart of Account ledgers alongside bank accounts (this module only)."""
        if self._schema_ready:
            return
        if not self.session.execute(
            text("SELECT OBJECT_ID(N'dbo.OthersBankCashTransaction', N'U')")
        ).scalar():
            self._schema_ready = True
            return

        needs_ledger_cols = not self._column_exists("CreditLedgerKey") or not self._column_exists(
            "DebitLedgerKey"
        )
        needs_nullable = not self._bank_account_nullable()

        if needs_ledger_cols:
            if not self._column_exists("CreditLedgerKey"):
                self.session.execute(
                    text(
                        """
                        ALTER TABLE dbo.OthersBankCashTransaction
                        ADD CreditLedgerKey NVARCHAR(40) NULL
                        """
                    )
                )
                self.session.commit()
            if not self._column_exists("DebitLedgerKey"):
                self.session.execute(
                    text(
                        """
                        ALTER TABLE dbo.OthersBankCashTransaction
                        ADD DebitLedgerKey NVARCHAR(40) NULL
                        """
                    )
                )
                self.session.commit()

        if needs_nullable:
            # Relax NOT NULL on bank FKs so CoA-only legs can be stored.
            self.session.execute(
                text(
                    """
                    IF EXISTS (
                        SELECT 1 FROM sys.check_constraints
                        WHERE name = N'CK_OthersBankCashTxn_Accounts'
                          AND parent_object_id = OBJECT_ID(N'dbo.OthersBankCashTransaction')
                    )
                        ALTER TABLE dbo.OthersBankCashTransaction
                        DROP CONSTRAINT CK_OthersBankCashTxn_Accounts;

                    IF EXISTS (
                        SELECT 1 FROM sys.foreign_keys
                        WHERE name = N'FK_OthersBankCashTxn_Credit'
                          AND parent_object_id = OBJECT_ID(N'dbo.OthersBankCashTransaction')
                    )
                        ALTER TABLE dbo.OthersBankCashTransaction
                        DROP CONSTRAINT FK_OthersBankCashTxn_Credit;

                    IF EXISTS (
                        SELECT 1 FROM sys.foreign_keys
                        WHERE name = N'FK_OthersBankCashTxn_Debit'
                          AND parent_object_id = OBJECT_ID(N'dbo.OthersBankCashTransaction')
                    )
                        ALTER TABLE dbo.OthersBankCashTransaction
                        DROP CONSTRAINT FK_OthersBankCashTxn_Debit;
                    """
                )
            )
            self.session.commit()

            self.session.execute(
                text(
                    """
                    ALTER TABLE dbo.OthersBankCashTransaction
                    ALTER COLUMN CreditBankAccountID INT NULL;
                    ALTER TABLE dbo.OthersBankCashTransaction
                    ALTER COLUMN DebitBankAccountID INT NULL;
                    """
                )
            )
            self.session.commit()

            self.session.execute(
                text(
                    """
                    IF NOT EXISTS (
                        SELECT 1 FROM sys.foreign_keys
                        WHERE name = N'FK_OthersBankCashTxn_Credit'
                          AND parent_object_id = OBJECT_ID(N'dbo.OthersBankCashTransaction')
                    )
                        ALTER TABLE dbo.OthersBankCashTransaction
                            ADD CONSTRAINT FK_OthersBankCashTxn_Credit
                            FOREIGN KEY (CreditBankAccountID)
                            REFERENCES dbo.JtcsBankAccountMaster (JtcsBankAccountID);

                    IF NOT EXISTS (
                        SELECT 1 FROM sys.foreign_keys
                        WHERE name = N'FK_OthersBankCashTxn_Debit'
                          AND parent_object_id = OBJECT_ID(N'dbo.OthersBankCashTransaction')
                    )
                        ALTER TABLE dbo.OthersBankCashTransaction
                            ADD CONSTRAINT FK_OthersBankCashTxn_Debit
                            FOREIGN KEY (DebitBankAccountID)
                            REFERENCES dbo.JtcsBankAccountMaster (JtcsBankAccountID);
                    """
                )
            )
            self.session.commit()

        if needs_ledger_cols or needs_nullable:
            self.session.execute(
                text(
                    """
                    UPDATE dbo.OthersBankCashTransaction
                    SET CreditLedgerKey = CONCAT(N'bank-', CreditBankAccountID)
                    WHERE CreditLedgerKey IS NULL AND CreditBankAccountID IS NOT NULL;

                    UPDATE dbo.OthersBankCashTransaction
                    SET DebitLedgerKey = CONCAT(N'bank-', DebitBankAccountID)
                    WHERE DebitLedgerKey IS NULL AND DebitBankAccountID IS NOT NULL;
                    """
                )
            )
            self.session.commit()

        self.session.execute(
            text(
                """
                IF NOT EXISTS (
                    SELECT 1 FROM sys.check_constraints
                    WHERE name = N'CK_OthersBankCashTxn_LedgerKeys'
                      AND parent_object_id = OBJECT_ID(N'dbo.OthersBankCashTransaction')
                )
                    ALTER TABLE dbo.OthersBankCashTransaction
                        ADD CONSTRAINT CK_OthersBankCashTxn_LedgerKeys
                        CHECK (
                            CreditLedgerKey IS NOT NULL
                            AND DebitLedgerKey IS NOT NULL
                            AND CreditLedgerKey <> DebitLedgerKey
                        );
                """
            )
        )
        self.session.commit()
        if not self._column_exists("InvoiceID"):
            self.session.execute(
                text(
                    """
                    ALTER TABLE dbo.OthersBankCashTransaction
                    ADD InvoiceID INT NULL
                    """
                )
            )
            self.session.commit()
        if not self._column_exists("InvoiceLinkMode"):
            self.session.execute(
                text(
                    """
                    ALTER TABLE dbo.OthersBankCashTransaction
                    ADD InvoiceLinkMode NVARCHAR(20) NULL
                    """
                )
            )
            self.session.commit()
        if not self._column_exists("CustomerID"):
            self.session.execute(
                text(
                    """
                    ALTER TABLE dbo.OthersBankCashTransaction
                    ADD CustomerID INT NULL
                    """
                )
            )
            self.session.commit()
        if not self._column_exists("WorkID"):
            self.session.execute(
                text(
                    """
                    ALTER TABLE dbo.OthersBankCashTransaction
                    ADD WorkID INT NULL
                    """
                )
            )
            self.session.commit()
        if not self._column_exists("WorkTypeID"):
            self.session.execute(
                text(
                    """
                    ALTER TABLE dbo.OthersBankCashTransaction
                    ADD WorkTypeID INT NULL
                    """
                )
            )
            self.session.commit()
        self.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.OthersBankCashInvoiceAllocation', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.OthersBankCashInvoiceAllocation (
                        AllocationID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                        EntryID INT NOT NULL,
                        InvoiceID INT NOT NULL,
                        AllocatedAmount DECIMAL(18, 2) NOT NULL,
                        AllocationSource NVARCHAR(20) NULL,
                        CONSTRAINT FK_OBCAlloc_Entry
                            FOREIGN KEY (EntryID) REFERENCES dbo.OthersBankCashTransaction (EntryID),
                        CONSTRAINT UQ_OBCAlloc_Entry_Invoice UNIQUE (EntryID, InvoiceID)
                    );
                END
                """
            )
        )
        self.session.commit()
        alloc_source = self.session.execute(
            text(
                """
                SELECT 1
                FROM sys.columns
                WHERE object_id = OBJECT_ID(N'dbo.OthersBankCashInvoiceAllocation')
                  AND name = N'AllocationSource'
                """
            )
        ).first()
        if not alloc_source:
            self.session.execute(
                text(
                    """
                    ALTER TABLE dbo.OthersBankCashInvoiceAllocation
                    ADD AllocationSource NVARCHAR(20) NULL
                    """
                )
            )
            self.session.commit()
        self._ensure_lookup_indexes()
        self._schema_ready = True

    def _ensure_lookup_indexes(self) -> None:
        """Equality lookups used by Money In/Out. Contains search is not indexed here."""
        statements = (
            """
            IF OBJECT_ID(N'dbo.OthersBankCashTransaction', N'U') IS NOT NULL
               AND NOT EXISTS (
                    SELECT 1 FROM sys.indexes
                    WHERE name = N'IX_OthersBankCashTxn_CustomerID'
                      AND object_id = OBJECT_ID(N'dbo.OthersBankCashTransaction')
               )
                CREATE INDEX IX_OthersBankCashTxn_CustomerID
                    ON dbo.OthersBankCashTransaction (CustomerID, IsActive);
            """,
            """
            IF OBJECT_ID(N'dbo.OthersBankCashTransaction', N'U') IS NOT NULL
               AND COL_LENGTH(N'dbo.OthersBankCashTransaction', N'InvoiceID') IS NOT NULL
               AND NOT EXISTS (
                    SELECT 1 FROM sys.indexes
                    WHERE name = N'IX_OthersBankCashTxn_InvoiceID'
                      AND object_id = OBJECT_ID(N'dbo.OthersBankCashTransaction')
               )
                CREATE INDEX IX_OthersBankCashTxn_InvoiceID
                    ON dbo.OthersBankCashTransaction (InvoiceID);
            """,
            """
            IF OBJECT_ID(N'dbo.OthersBankCashInvoiceAllocation', N'U') IS NOT NULL
               AND NOT EXISTS (
                    SELECT 1 FROM sys.indexes
                    WHERE name = N'IX_OBCAlloc_InvoiceID'
                      AND object_id = OBJECT_ID(N'dbo.OthersBankCashInvoiceAllocation')
               )
                CREATE INDEX IX_OBCAlloc_InvoiceID
                    ON dbo.OthersBankCashInvoiceAllocation (InvoiceID)
                    INCLUDE (EntryID, AllocatedAmount);
            """,
        )
        for statement in statements:
            self.session.execute(text(statement))
            self.session.commit()

    def list_active(self, *, limit: int = 200) -> list[OthersBankCashTransaction]:
        self.ensure_schema()
        stmt = (
            select(OthersBankCashTransaction)
            .where(OthersBankCashTransaction.IsActive == True)  # noqa: E712
            .order_by(
                OthersBankCashTransaction.WorkDate.desc(),
                OthersBankCashTransaction.EntryID.desc(),
            )
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())

    def get_by_id(self, entry_id: int) -> OthersBankCashTransaction | None:
        self.ensure_schema()
        return self.session.get(OthersBankCashTransaction, entry_id)

    def create(self, data: dict) -> OthersBankCashTransaction:
        self.ensure_schema()
        data.setdefault("CreatedDate", datetime.utcnow())
        data.setdefault("IsActive", True)
        row = OthersBankCashTransaction(**data)
        self.session.add(row)
        self.session.flush()
        return row

    def update(self, row: OthersBankCashTransaction, data: dict) -> OthersBankCashTransaction:
        self.ensure_schema()
        preserve = {"EntryID", "CreatedDate", "CreatedBy", "VoucherNo"}
        for key, value in data.items():
            if key not in preserve:
                setattr(row, key, value)
        self.session.flush()
        return row

    def soft_delete(self, row: OthersBankCashTransaction) -> None:
        row.IsActive = False
        self.session.flush()

    def next_voucher_no(self, work_date) -> str:
        prefix = f"OBC-{work_date.strftime('%Y%m%d')}-"
        stmt = (
            select(OthersBankCashTransaction.VoucherNo)
            .where(OthersBankCashTransaction.VoucherNo.like(f"{prefix}%"))
            .order_by(OthersBankCashTransaction.VoucherNo.desc())
        )
        last = self.session.scalars(stmt).first()
        seq = 1
        if last:
            try:
                seq = int(str(last).rsplit("-", 1)[-1]) + 1
            except ValueError:
                seq = 1
        return f"{prefix}{seq:04d}"

    def list_ledger_accounts(self, *, active_only: bool = True) -> list[JtcsBankAccountMaster]:
        stmt = select(JtcsBankAccountMaster).order_by(
            JtcsBankAccountMaster.AccountType,
            JtcsBankAccountMaster.BankName,
            JtcsBankAccountMaster.JtcsBankAccountID,
        )
        if active_only:
            stmt = stmt.where(JtcsBankAccountMaster.ActiveStatus == True)  # noqa: E712
        return list(self.session.scalars(stmt).all())

    def list_transfer_ledgers(self) -> list[dict]:
        """Bank + Chart of Account ledgers under Assets/Liabilities chart groups."""
        self.ensure_schema()
        from app.repositories.bank_master_repository import BankMasterRepository
        from app.repositories.chart_account_repository import ChartAccountRepository
        from app.repositories.chart_group_repository import ChartGroupRepository

        BankMasterRepository(self.session).ensure_schema()
        try:
            ChartGroupRepository(self.session).ensure_schema()
            ChartAccountRepository(self.session).ensure_schema()
        except Exception:
            self.session.rollback()

        bank_sql = """
            SELECT
                CONCAT(N'bank-', b.JtcsBankAccountID) AS ledger_key,
                N'bank' AS source,
                b.JtcsBankAccountID AS bank_account_id,
                CAST(NULL AS INT) AS coa_account_id,
                b.BankName AS ledger_name,
                ISNULL(b.MaskedAccountNumber, b.AccountNumber) AS account_ref,
                ISNULL(NULLIF(LTRIM(RTRIM(b.AccountType)), N''), N'OTH') AS account_type,
                g.GroupID AS group_id,
                ISNULL(g.GroupName, N'Ungrouped') AS group_name,
                ISNULL(g.UnderType, N'Assets') AS under_type,
                CASE WHEN UPPER(LTRIM(RTRIM(ISNULL(b.BankName, N'')))) = N'CASH' THEN 1 ELSE 0 END AS is_cash,
                CASE WHEN UPPER(LTRIM(RTRIM(ISNULL(b.AccountType, N'')))) = N'RD' THEN 1 ELSE 0 END AS is_rd,
                CAST(NULL AS INT) AS customer_id,
                CAST(NULL AS NVARCHAR(255)) AS customer_name
            FROM dbo.JtcsBankAccountMaster b
            LEFT JOIN dbo.ChartOfGroupMaster g ON g.GroupID = b.ChartGroupID AND g.IsActive = 1
            WHERE ISNULL(b.ActiveStatus, 1) = 1
              AND (
                    b.ChartGroupID IS NULL
                 OR g.UnderType IN (N'Assets', N'Liabilities')
              )
        """
        coa_sql = """
            SELECT
                CONCAT(N'coa-', a.AccountID) AS ledger_key,
                N'coa' AS source,
                CAST(NULL AS INT) AS bank_account_id,
                a.AccountID AS coa_account_id,
                a.AccountName AS ledger_name,
                CASE
                    WHEN a.WorkID IS NOT NULL THEN N'Work'
                    WHEN a.CustomerID IS NOT NULL THEN N'Customer'
                    ELSE N'Ledger'
                END AS account_ref,
                CASE
                    WHEN a.WorkID IS NOT NULL THEN N'WORK'
                    WHEN a.CustomerID IS NOT NULL THEN N'CUST'
                    ELSE N'COA'
                END AS account_type,
                g.GroupID AS group_id,
                g.GroupName AS group_name,
                g.UnderType AS under_type,
                0 AS is_cash,
                0 AS is_rd,
                a.CustomerID AS customer_id,
                c.CustomerName AS customer_name
            FROM dbo.ChartOfAccountMaster a
            INNER JOIN dbo.ChartOfGroupMaster g ON g.GroupID = a.GroupID
            LEFT JOIN dbo.CustomerMaster c ON c.CustomerID = a.CustomerID
            WHERE a.IsActive = 1
              AND g.IsActive = 1
              AND g.UnderType IN (N'Assets', N'Liabilities')
        """
        has_coa = bool(
            self.session.execute(
                text("SELECT OBJECT_ID(N'dbo.ChartOfAccountMaster', N'U')")
            ).scalar()
        )
        sql = bank_sql
        if has_coa:
            sql = f"{bank_sql}\nUNION ALL\n{coa_sql}"
        sql = f"{sql}\nORDER BY under_type, group_name, ledger_name, ledger_key"
        rows = self.session.execute(text(sql)).mappings().all()
        return [dict(r) for r in rows]

    def _column_names(self, table: str) -> set[str]:
        rows = self.session.execute(
            text("SELECT name FROM sys.columns WHERE object_id = OBJECT_ID(:obj)"),
            {"obj": f"dbo.{table}"},
        ).all()
        return {str(row[0]) for row in rows}

    @staticmethod
    def _like(expr: str) -> str:
        return f"UPPER({expr}) LIKE UPPER(:like)"

    def search_transfer_ledgers(
        self,
        term: str,
        *,
        limit: int = 30,
        include_customers: bool = False,
    ) -> list[dict]:
        """Eligible bank and chart ledgers whose existing fields contain the term.

        Same Assets/Liabilities eligibility as list_transfer_ledgers. The match is
        a case-insensitive substring (LIKE '%term%'). A B-tree cannot seek that
        pattern, so this stays a short parameterized scan of the ledger set.

        include_customers is only for Money In-Out Credit Account search. It adds
        active Customer Master rows that do not already have a chart ledger.
        Debit search leaves this off, so bank and chart results stay unchanged.
        """
        self.ensure_schema()
        needle = " ".join((term or "").split())
        if not needle:
            return []
        limit = max(1, min(int(limit or 30), 50))
        bank_cols = self._column_names("JtcsBankAccountMaster")
        coa_cols = self._column_names("ChartOfAccountMaster")
        cust_cols = self._column_names("CustomerMaster")
        has_coa = "AccountID" in coa_cols and "AccountName" in coa_cols

        def present(cols: set[str], name: str, expr: str) -> str | None:
            if name not in cols:
                return None
            return self._like(expr)

        bank_preds = [
            self._like("b.BankName"),
            self._like("CAST(b.JtcsBankAccountID AS NVARCHAR(20))"),
        ]
        for column, expr in (
            ("AccountNumber", "b.AccountNumber"),
            ("MaskedAccountNumber", "b.MaskedAccountNumber"),
            ("IFSCCode", "b.IFSCCode"),
            ("AccountHolderName", "b.AccountHolderName"),
            ("BranchName", "b.BranchName"),
            ("UpiId", "b.UpiId"),
        ):
            clause = present(bank_cols, column, expr)
            if clause:
                bank_preds.append(clause)

        bank_sql = f"""
            SELECT
                CONCAT(N'bank-', b.JtcsBankAccountID) AS ledger_key,
                N'bank' AS source,
                b.JtcsBankAccountID AS bank_account_id,
                CAST(NULL AS INT) AS coa_account_id,
                b.BankName AS ledger_name,
                ISNULL(b.MaskedAccountNumber, b.AccountNumber) AS account_ref,
                ISNULL(NULLIF(LTRIM(RTRIM(b.AccountType)), N''), N'OTH') AS account_type,
                ISNULL(g.GroupName, N'Ungrouped') AS group_name,
                CAST(NULL AS INT) AS customer_id,
                CAST(NULL AS NVARCHAR(255)) AS customer_name,
                CAST(NULL AS NVARCHAR(30)) AS mobile,
                CAST(NULL AS NVARCHAR(20)) AS pan,
                CAST(NULL AS NVARCHAR(20)) AS gstin,
                ISNULL(b.IFSCCode, N'') AS ifsc,
                ISNULL(b.AccountNumber, N'') AS account_number
            FROM dbo.JtcsBankAccountMaster b
            LEFT JOIN dbo.ChartOfGroupMaster g ON g.GroupID = b.ChartGroupID AND g.IsActive = 1
            WHERE ISNULL(b.ActiveStatus, 1) = 1
              AND (
                    b.ChartGroupID IS NULL
                 OR g.UnderType IN (N'Assets', N'Liabilities')
              )
              AND ({' OR '.join(bank_preds)})
        """
        parts = [bank_sql]
        if has_coa:
            coa_preds = [
                self._like("a.AccountName"),
                self._like("CAST(a.AccountID AS NVARCHAR(20))"),
            ]
            if "CustomerID" in coa_cols:
                coa_preds.append(self._like("CAST(a.CustomerID AS NVARCHAR(20))"))
            if "GroupName" in self._column_names("ChartOfGroupMaster"):
                coa_preds.append(self._like("g.GroupName"))
            for column, expr in (
                ("CustomerName", "c.CustomerName"),
                ("MobileNumber", "c.MobileNumber"),
                ("AlternateMobile", "c.AlternateMobile"),
                ("WhatsAppNumber", "c.WhatsAppNumber"),
                ("PANNumber", "c.PANNumber"),
                ("GSTNumber", "c.GSTNumber"),
                ("AadhaarNumber", "c.AadhaarNumber"),
                ("EmployeeCode", "c.EmployeeCode"),
                ("EmailID", "c.EmailID"),
                ("BankName", "c.BankName"),
                ("AccountNumber", "c.AccountNumber"),
                ("IFSCCode", "c.IFSCCode"),
                ("AccountHolderName", "c.AccountHolderName"),
            ):
                clause = present(cust_cols, column, expr)
                if clause:
                    coa_preds.append(clause)
            mobile_sql = "c.MobileNumber" if "MobileNumber" in cust_cols else "CAST(NULL AS NVARCHAR(30))"
            pan_sql = "c.PANNumber" if "PANNumber" in cust_cols else "CAST(NULL AS NVARCHAR(20))"
            gst_sql = "c.GSTNumber" if "GSTNumber" in cust_cols else "CAST(NULL AS NVARCHAR(20))"
            ifsc_sql = "ISNULL(c.IFSCCode, N'')" if "IFSCCode" in cust_cols else "N''"
            acct_sql = "ISNULL(c.AccountNumber, N'')" if "AccountNumber" in cust_cols else "N''"
            name_sql = "c.CustomerName" if "CustomerName" in cust_cols else "CAST(NULL AS NVARCHAR(255))"
            customer_id_sql = "a.CustomerID" if "CustomerID" in coa_cols else "CAST(NULL AS INT)"
            coa_sql = f"""
                SELECT
                    CONCAT(N'coa-', a.AccountID) AS ledger_key,
                    N'coa' AS source,
                    CAST(NULL AS INT) AS bank_account_id,
                    a.AccountID AS coa_account_id,
                    a.AccountName AS ledger_name,
                    CASE
                        WHEN a.WorkID IS NOT NULL THEN N'Work'
                        WHEN a.CustomerID IS NOT NULL THEN N'Customer'
                        ELSE N'Ledger'
                    END AS account_ref,
                    CASE
                        WHEN a.WorkID IS NOT NULL THEN N'WORK'
                        WHEN a.CustomerID IS NOT NULL THEN N'CUST'
                        ELSE N'COA'
                    END AS account_type,
                    g.GroupName AS group_name,
                    {customer_id_sql} AS customer_id,
                    {name_sql} AS customer_name,
                    {mobile_sql} AS mobile,
                    {pan_sql} AS pan,
                    {gst_sql} AS gstin,
                    {ifsc_sql} AS ifsc,
                    {acct_sql} AS account_number
                FROM dbo.ChartOfAccountMaster a
                INNER JOIN dbo.ChartOfGroupMaster g ON g.GroupID = a.GroupID
                LEFT JOIN dbo.CustomerMaster c ON c.CustomerID = a.CustomerID
                WHERE a.IsActive = 1
                  AND g.IsActive = 1
                  AND g.UnderType IN (N'Assets', N'Liabilities')
                  AND ({' OR '.join(coa_preds)})
            """
            parts.append(coa_sql)
        if include_customers and "CustomerID" in cust_cols and "CustomerName" in cust_cols:
            customer_preds = [
                self._like("LTRIM(RTRIM(c.CustomerName))"),
                self._like("CAST(c.CustomerID AS NVARCHAR(20))"),
            ]
            for column, expr in (
                ("MobileNumber", "c.MobileNumber"),
                ("AlternateMobile", "c.AlternateMobile"),
                ("WhatsAppNumber", "c.WhatsAppNumber"),
                ("PANNumber", "c.PANNumber"),
                ("GSTNumber", "c.GSTNumber"),
                ("AadhaarNumber", "c.AadhaarNumber"),
                ("EmployeeCode", "c.EmployeeCode"),
                ("EmailID", "c.EmailID"),
            ):
                clause = present(cust_cols, column, f"LTRIM(RTRIM({expr}))")
                if clause:
                    customer_preds.append(clause)
            mobile_sql = "c.MobileNumber" if "MobileNumber" in cust_cols else "CAST(NULL AS NVARCHAR(30))"
            pan_sql = "c.PANNumber" if "PANNumber" in cust_cols else "CAST(NULL AS NVARCHAR(20))"
            gst_sql = "c.GSTNumber" if "GSTNumber" in cust_cols else "CAST(NULL AS NVARCHAR(20))"
            customer_sql = f"""
                SELECT
                    CONCAT(N'customer-', c.CustomerID) AS ledger_key,
                    N'customer' AS source,
                    CAST(NULL AS INT) AS bank_account_id,
                    CAST(NULL AS INT) AS coa_account_id,
                    LTRIM(RTRIM(c.CustomerName)) AS ledger_name,
                    N'Customer' AS account_ref,
                    N'CUST' AS account_type,
                    N'Customer' AS group_name,
                    c.CustomerID AS customer_id,
                    LTRIM(RTRIM(c.CustomerName)) AS customer_name,
                    {mobile_sql} AS mobile,
                    {pan_sql} AS pan,
                    {gst_sql} AS gstin,
                    N'' AS ifsc,
                    N'' AS account_number
                FROM dbo.CustomerMaster c
                WHERE ISNULL(c.CustomerStatus, N'Active') NOT IN (N'Inactive', N'Rejected')
                  AND NOT EXISTS (
                        SELECT 1
                        FROM dbo.ChartOfAccountMaster a
                        INNER JOIN dbo.ChartOfGroupMaster g ON g.GroupID = a.GroupID
                        WHERE a.CustomerID = c.CustomerID
                          AND ISNULL(a.IsActive, 1) = 1
                          AND ISNULL(g.IsActive, 1) = 1
                          AND g.UnderType IN (N'Assets', N'Liabilities')
                  )
                  AND ({' OR '.join(customer_preds)})
            """
            parts.append(customer_sql)
        sql = (
            "SELECT TOP (:lim) * FROM ("
            + "\nUNION ALL\n".join(parts)
            + ") AS ledgers ORDER BY ledger_name, ledger_key"
        )
        rows = self.session.execute(text(sql), {"like": f"%{needle}%", "lim": limit}).mappings().all()
        return [dict(row) for row in rows]
