from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from app.extensions import db
from app.repositories.shcil_wallet_opening_repository import ShcilWalletOpeningRepository


@dataclass
class ReportFilters:
    start_date: date
    end_date: date
    customer_id: int | None = None
    work_type: str | None = None
    bank_name: str | None = None


class ReportService:
    """All reports read only from JTCSDailyTransaction and JtcsBankTransaction."""

    REPORTS = {
        "daily-collection": "Daily Collection",
        "cash-book": "Cash Book",
        "bank-book": "Bank Book",
        "income": "Income Report",
        "expense": "Expense Report",
        "work-wise": "Work Wise Report",
        "customer-ledger": "Customer Ledger",
        "payment-mode": "Payment Mode Report",
        "cash-flow": "Cash Flow",
        "bank-balance": "Bank Balance",
        "outstanding": "Outstanding",
        "stamp-register": "Stamp Register",
        "stamp-sales": "Daily Stamp Sale",
        "stamp-daily-sale": "Daily Stamp Sale",
        "stamp-collection": "Stamp Collection",
        "stamp-customer-wise": "Customer Wise Stamp",
        "stamp-certificate-wise": "Certificate Wise Stamp",
        "stamp-date-wise": "Date Wise Stamp",
        "stamp-payment-mode": "Payment Mode Wise Stamp",
    }

    STAMP_FILTER = "AND d.WorkType = N'SHCIL' AND d.SubWorkType = N'Stamp Activity'"
    SHCIL_WALLET_ACCOUNT = "58250200000396"
    SHCIL_RECEIPT_SOURCE_TYPES = (
        "SHCIL",
        "ITR",
        "GST",
        "DSC",
        "TDS",
        "Income",
        "Expense",
        "Others",
        "Printing",
    )

    def list_reports(self) -> dict[str, str]:
        return self.REPORTS

    def run(self, report_key: str, filters: ReportFilters) -> dict[str, Any]:
        handlers = {
            "daily-collection": self.daily_collection,
            "cash-book": self.cash_book,
            "bank-book": self.bank_book,
            "income": self.income_report,
            "expense": self.expense_report,
            "work-wise": self.work_wise_report,
            "customer-ledger": self.customer_ledger,
            "payment-mode": self.payment_mode_report,
            "cash-flow": self.cash_flow,
            "bank-balance": self.bank_balance,
            "outstanding": self.outstanding_report,
            "stamp-register": self.stamp_register,
            "stamp-sales": self.stamp_sales,
            "stamp-daily-sale": self.stamp_sales,
            "stamp-collection": self.stamp_collection,
            "stamp-customer-wise": self.stamp_customer_wise,
            "stamp-certificate-wise": self.stamp_certificate_wise,
            "stamp-date-wise": self.stamp_date_wise,
            "stamp-payment-mode": self.stamp_payment_mode,
        }
        handler = handlers.get(report_key)
        if handler is None:
            raise ValueError("Unknown report.")
        return handler(filters)

    def daily_collection(self, filters: ReportFilters) -> dict[str, Any]:
        rows = db.session.execute(
            text(
                """
                SELECT TransactionDate,
                       ISNULL(SUM(ISNULL(Debit, 0)), 0) AS collection_amount,
                       COUNT(*) AS txn_count
                FROM JtcsBankTransaction
                WHERE TransactionDate BETWEEN :start_date AND :end_date
                  AND ISNULL(Debit, 0) > 0
                GROUP BY TransactionDate
                ORDER BY TransactionDate
                """
            ),
            {"start_date": filters.start_date, "end_date": filters.end_date},
        ).mappings().all()
        total = sum(Decimal(str(row["collection_amount"])) for row in rows)
        return {"title": self.REPORTS["daily-collection"], "rows": rows, "total": total}

    def cash_book(self, filters: ReportFilters) -> dict[str, Any]:
        rows = db.session.execute(
            text(
                """
                SELECT TransactionDate, Description, Debit, Credit, Remarks,
                       JtcsBankTransactionID
                FROM JtcsBankTransaction
                WHERE BankName = N'Cash'
                  AND TransactionDate BETWEEN :start_date AND :end_date
                ORDER BY TransactionDate, JtcsBankTransactionID
                """
            ),
            {"start_date": filters.start_date, "end_date": filters.end_date},
        ).mappings().all()
        return {"title": self.REPORTS["cash-book"], "rows": rows}

    def bank_book(self, filters: ReportFilters) -> dict[str, Any]:
        params = {"start_date": filters.start_date, "end_date": filters.end_date}
        bank_filter = ""
        if filters.bank_name:
            bank_filter = "AND BankName = :bank_name"
            params["bank_name"] = filters.bank_name

        rows = db.session.execute(
            text(
                f"""
                SELECT TransactionDate, BankName, Description, Debit, Credit, Remarks,
                       JtcsBankTransactionID
                FROM JtcsBankTransaction
                WHERE BankName <> N'Cash'
                  AND TransactionDate BETWEEN :start_date AND :end_date
                  {bank_filter}
                ORDER BY BankName, TransactionDate, JtcsBankTransactionID
                """
            ),
            params,
        ).mappings().all()
        return {"title": self.REPORTS["bank-book"], "rows": rows}

    def income_report(self, filters: ReportFilters) -> dict[str, Any]:
        rows = db.session.execute(
            text(
                """
                SELECT TransactionDate, WorkType, SubWorkType, CustomerName,
                       IncomeAmount, SaleAmount, Description, TransactionID
                FROM JTCSDailyTransaction
                WHERE TransactionDate BETWEEN :start_date AND :end_date
                  AND Status = N'Posted'
                  AND (IncomeAmount > 0 OR SaleAmount > 0)
                ORDER BY TransactionDate, TransactionID
                """
            ),
            {"start_date": filters.start_date, "end_date": filters.end_date},
        ).mappings().all()
        total = sum(
            Decimal(str(row["IncomeAmount"])) + Decimal(str(row["SaleAmount"])) for row in rows
        )
        return {"title": self.REPORTS["income"], "rows": rows, "total": total}

    def expense_report(self, filters: ReportFilters) -> dict[str, Any]:
        rows = db.session.execute(
            text(
                """
                SELECT TransactionDate, WorkType, SubWorkType, CustomerName,
                       ExpenseAmount, PurchaseAmount, Description, TransactionID
                FROM JTCSDailyTransaction
                WHERE TransactionDate BETWEEN :start_date AND :end_date
                  AND Status = N'Posted'
                  AND (ExpenseAmount > 0 OR PurchaseAmount > 0)
                ORDER BY TransactionDate, TransactionID
                """
            ),
            {"start_date": filters.start_date, "end_date": filters.end_date},
        ).mappings().all()
        total = sum(
            Decimal(str(row["ExpenseAmount"])) + Decimal(str(row["PurchaseAmount"])) for row in rows
        )
        return {"title": self.REPORTS["expense"], "rows": rows, "total": total}

    def work_wise_report(self, filters: ReportFilters) -> dict[str, Any]:
        params = {"start_date": filters.start_date, "end_date": filters.end_date}
        work_filter = ""
        if filters.work_type:
            work_filter = "AND WorkType = :work_type"
            params["work_type"] = filters.work_type

        rows = db.session.execute(
            text(
                f"""
                SELECT WorkType, SubWorkType,
                       COUNT(*) AS txn_count,
                       ISNULL(SUM(IncomeAmount + SaleAmount), 0) AS total_income,
                       ISNULL(SUM(ExpenseAmount + PurchaseAmount), 0) AS total_expense,
                       ISNULL(SUM(TotalAmount), 0) AS total_amount
                FROM JTCSDailyTransaction
                WHERE TransactionDate BETWEEN :start_date AND :end_date
                  AND Status = N'Posted'
                  {work_filter}
                GROUP BY WorkType, SubWorkType
                ORDER BY WorkType, SubWorkType
                """
            ),
            params,
        ).mappings().all()
        return {"title": self.REPORTS["work-wise"], "rows": rows}

    def customer_ledger(self, filters: ReportFilters) -> dict[str, Any]:
        params = {
            "start_date": filters.start_date,
            "end_date": filters.end_date,
            "customer_id": filters.customer_id,
        }
        customer_filter = ""
        if filters.customer_id:
            customer_filter = "AND d.CustomerID = :customer_id"

        rows = db.session.execute(
            text(
                f"""
                SELECT d.TransactionDate, d.CustomerID, d.CustomerName, d.WorkType,
                       d.IncomeAmount, d.ExpenseAmount, d.SaleAmount, d.PurchaseAmount,
                       d.TotalAmount, d.Description, d.TransactionID,
                       b.Debit AS money_in, b.Credit AS money_out
                FROM JTCSDailyTransaction d
                LEFT JOIN JtcsBankTransaction b
                    ON b.JtcsBankTransactionID = d.BankTransactionID
                WHERE d.TransactionDate BETWEEN :start_date AND :end_date
                  AND d.Status = N'Posted'
                  {customer_filter}
                ORDER BY d.CustomerName, d.TransactionDate, d.TransactionID
                """
            ),
            params,
        ).mappings().all()
        return {"title": self.REPORTS["customer-ledger"], "rows": rows}

    def payment_mode_report(self, filters: ReportFilters) -> dict[str, Any]:
        rows = db.session.execute(
            text(
                """
                SELECT pm.PaymentModeName,
                       COUNT(d.TransactionID) AS txn_count,
                       ISNULL(SUM(d.IncomeAmount + d.SaleAmount), 0) AS receipts,
                       ISNULL(SUM(d.ExpenseAmount + d.PurchaseAmount), 0) AS payments
                FROM JTCSDailyTransaction d
                LEFT JOIN PaymentModeMaster pm ON pm.PaymentModeID = d.PaymentModeID
                WHERE d.TransactionDate BETWEEN :start_date AND :end_date
                  AND d.Status = N'Posted'
                GROUP BY pm.PaymentModeName
                ORDER BY pm.PaymentModeName
                """
            ),
            {"start_date": filters.start_date, "end_date": filters.end_date},
        ).mappings().all()
        return {"title": self.REPORTS["payment-mode"], "rows": rows}

    def cash_flow(self, filters: ReportFilters) -> dict[str, Any]:
        rows = db.session.execute(
            text(
                """
                SELECT TransactionDate,
                       ISNULL(SUM(ISNULL(Debit, 0)), 0) AS money_in,
                       ISNULL(SUM(ISNULL(Credit, 0)), 0) AS money_out,
                       ISNULL(SUM(ISNULL(Debit, 0)), 0) - ISNULL(SUM(ISNULL(Credit, 0)), 0) AS net_flow
                FROM JtcsBankTransaction
                WHERE TransactionDate BETWEEN :start_date AND :end_date
                GROUP BY TransactionDate
                ORDER BY TransactionDate
                """
            ),
            {"start_date": filters.start_date, "end_date": filters.end_date},
        ).mappings().all()
        return {"title": self.REPORTS["cash-flow"], "rows": rows}

    def bank_balance(self, filters: ReportFilters) -> dict[str, Any]:
        del filters
        rows = db.session.execute(
            text(
                """
                SELECT BankName,
                       ISNULL(SUM(ISNULL(Debit, 0)), 0) AS total_in,
                       ISNULL(SUM(ISNULL(Credit, 0)), 0) AS total_out,
                       ISNULL(SUM(ISNULL(Debit, 0)), 0) - ISNULL(SUM(ISNULL(Credit, 0)), 0) AS balance
                FROM JtcsBankTransaction
                GROUP BY BankName
                ORDER BY BankName
                """
            )
        ).mappings().all()
        return {"title": self.REPORTS["bank-balance"], "rows": rows}

    def outstanding_report(self, filters: ReportFilters) -> dict[str, Any]:
        params = {"start_date": filters.start_date, "end_date": filters.end_date}
        customer_filter = ""
        if filters.customer_id:
            customer_filter = "AND d.CustomerID = :customer_id"
            params["customer_id"] = filters.customer_id

        rows = db.session.execute(
            text(
                f"""
                SELECT d.CustomerID,
                       d.CustomerName,
                       ISNULL(SUM(d.IncomeAmount + d.SaleAmount), 0) AS billed,
                       ISNULL(SUM(ISNULL(b.Debit, 0)), 0) AS collected,
                       ISNULL(SUM(d.IncomeAmount + d.SaleAmount), 0)
                           - ISNULL(SUM(ISNULL(b.Debit, 0)), 0) AS outstanding
                FROM JTCSDailyTransaction d
                LEFT JOIN JtcsBankTransaction b
                    ON b.JtcsBankTransactionID = d.BankTransactionID
                WHERE d.TransactionDate BETWEEN :start_date AND :end_date
                  AND d.Status = N'Posted'
                  AND d.CustomerID IS NOT NULL
                  {customer_filter}
                GROUP BY d.CustomerID, d.CustomerName
                HAVING ISNULL(SUM(d.IncomeAmount + d.SaleAmount), 0)
                     - ISNULL(SUM(ISNULL(b.Debit, 0)), 0) <> 0
                ORDER BY d.CustomerName
                """
            ),
            params,
        ).mappings().all()
        return {"title": self.REPORTS["outstanding"], "rows": rows}

    def stamp_register(self, filters: ReportFilters) -> dict[str, Any]:
        rows = db.session.execute(
            text(
                f"""
                SELECT s.CertificateNumber,
                       s.CertificateIssuedDate,
                       s.AccountReference,
                       s.UniqueDocumentReference,
                       s.PurchasedBy,
                       s.ConsiderationPrice,
                       s.StampDutyAmount,
                       s.FirstPartyName,
                       s.SecondPartyName,
                       d.TransactionDate,
                       d.SaleAmount,
                       pm.PaymentModeName,
                       d.CustomerName,
                       d.ReferenceNo,
                       d.TransactionID,
                       s.StampID
                FROM StampMaster s
                INNER JOIN JTCSDailyTransaction d ON d.StampID = s.StampID
                LEFT JOIN PaymentModeMaster pm ON pm.PaymentModeID = d.PaymentModeID
                WHERE d.TransactionDate BETWEEN :start_date AND :end_date
                  AND d.Status = N'Posted'
                  {self.STAMP_FILTER}
                ORDER BY d.TransactionDate DESC, s.CertificateNumber
                """
            ),
            {"start_date": filters.start_date, "end_date": filters.end_date},
        ).mappings().all()
        total = sum(Decimal(str(row["SaleAmount"] or 0)) for row in rows)
        return {"title": self.REPORTS["stamp-register"], "rows": rows, "total": total}

    def stamp_sales(self, filters: ReportFilters) -> dict[str, Any]:
        rows = db.session.execute(
            text(
                f"""
                SELECT d.TransactionDate,
                       s.CertificateNumber,
                       d.CustomerName,
                       d.SaleAmount,
                       pm.PaymentModeName,
                       d.ReferenceNo,
                       d.TransactionID
                FROM JTCSDailyTransaction d
                INNER JOIN StampMaster s ON s.StampID = d.StampID
                LEFT JOIN PaymentModeMaster pm ON pm.PaymentModeID = d.PaymentModeID
                WHERE d.TransactionDate BETWEEN :start_date AND :end_date
                  AND d.Status = N'Posted'
                  {self.STAMP_FILTER}
                ORDER BY d.TransactionDate, d.TransactionID
                """
            ),
            {"start_date": filters.start_date, "end_date": filters.end_date},
        ).mappings().all()
        total = sum(Decimal(str(row["SaleAmount"] or 0)) for row in rows)
        return {"title": self.REPORTS["stamp-sales"], "rows": rows, "total": total}

    def _shcil_opening_repo(self) -> ShcilWalletOpeningRepository:
        repo = getattr(self, "_opening_repo", None)
        if repo is None:
            repo = ShcilWalletOpeningRepository()
            self._opening_repo = repo
        return repo

    def get_shcil_opening_balance(self) -> dict[str, Any] | None:
        row = self._shcil_opening_repo().get_by_account(self.SHCIL_WALLET_ACCOUNT)
        if row is None:
            return None
        return {
            "opening_balance": self._decimal_value(row.OpeningBalance),
            "opening_balance_date": row.OpeningBalanceDate,
            "updated_by": row.UpdatedBy,
            "updated_date": row.UpdatedDate,
        }

    def save_shcil_opening_balance(
        self,
        *,
        opening_balance: Decimal,
        opening_balance_date: date,
        updated_by: str,
    ) -> dict[str, Any]:
        if opening_balance < 0:
            raise ValueError("Opening balance cannot be negative.")
        row = self._shcil_opening_repo().save(
            account_number=self.SHCIL_WALLET_ACCOUNT,
            opening_balance=opening_balance,
            opening_balance_date=opening_balance_date,
            updated_by=updated_by,
        )
        db.session.commit()
        return {
            "opening_balance": self._decimal_value(row.OpeningBalance),
            "opening_balance_date": row.OpeningBalanceDate,
            "updated_by": row.UpdatedBy,
            "updated_date": row.UpdatedDate,
        }

    def _shcil_wallet_account(self) -> dict[str, Any] | None:
        row = db.session.execute(
            text(
                """
                SELECT TOP 1 JtcsBankAccountID,
                       BankName,
                       AccountNumber,
                       ISNULL(OpeningBalance, 0) AS OpeningBalance,
                       OpeningBalanceDate
                FROM JtcsBankAccountMaster
                WHERE AccountNumber = :account_number
                   OR RIGHT(REPLACE(REPLACE(ISNULL(AccountNumber, N''), N' ', N''), N'-', N''), 4) = N'0396'
                ORDER BY CASE WHEN AccountNumber = :account_number THEN 0 ELSE 1 END,
                         JtcsBankAccountID
                """
            ),
            {"account_number": self.SHCIL_WALLET_ACCOUNT},
        ).mappings().first()
        return dict(row) if row else None

    @staticmethod
    def _decimal_value(value: Any) -> Decimal:
        if value is None:
            return Decimal("0")
        return Decimal(str(value))

    def _shcil_wallet_deposits(
        self,
        *,
        account_id: int,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"account_id": account_id}
        date_filter = ""
        if start_date is not None and end_date is not None:
            date_filter = "AND b.TransactionDate BETWEEN :start_date AND :end_date"
            params["start_date"] = start_date
            params["end_date"] = end_date
        elif start_date is not None:
            date_filter = "AND b.TransactionDate >= :start_date"
            params["start_date"] = start_date
        elif end_date is not None:
            date_filter = "AND b.TransactionDate <= :end_date"
            params["end_date"] = end_date

        source_types = ", ".join(f"N'{name}'" for name in self.SHCIL_RECEIPT_SOURCE_TYPES)
        rows = db.session.execute(
            text(
                f"""
                SELECT b.TransactionDate,
                       b.Description,
                       b.Debit AS DepositAmount,
                       b.Remarks,
                       b.JtcsBankTransactionID
                FROM JtcsBankTransaction b
                WHERE b.JtcsBankAccountID = :account_id
                  AND ISNULL(b.Debit, 0) > 0
                  AND NOT (
                      ISNULL(b.SourceType, N'') IN ({source_types})
                      AND ISNULL(b.LedgerKind, N'') = N'RECEIPT'
                  )
                  {date_filter}
                ORDER BY b.TransactionDate, b.JtcsBankTransactionID
                """
            ),
            params,
        ).mappings().all()
        return [dict(row) for row in rows]

    def _shcil_stamp_prints(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        date_filter = ""
        if start_date is not None and end_date is not None:
            date_filter = (
                "AND COALESCE(s.CertificateIssuedDate, d.TransactionDate) "
                "BETWEEN :start_date AND :end_date"
            )
            params["start_date"] = start_date
            params["end_date"] = end_date
        elif start_date is not None:
            date_filter = (
                "AND COALESCE(s.CertificateIssuedDate, d.TransactionDate) >= :start_date"
            )
            params["start_date"] = start_date
        elif end_date is not None:
            date_filter = (
                "AND COALESCE(s.CertificateIssuedDate, d.TransactionDate) <= :end_date"
            )
            params["end_date"] = end_date

        rows = db.session.execute(
            text(
                f"""
                SELECT COALESCE(s.CertificateIssuedDate, d.TransactionDate) AS EventDate,
                       s.CertificateNumber,
                       s.StampDutyAmount AS StampUsed,
                       d.TransactionID
                FROM StampMaster s
                INNER JOIN JTCSDailyTransaction d ON d.StampID = s.StampID
                WHERE d.Status = N'Posted'
                  {self.STAMP_FILTER}
                  AND ISNULL(s.StampDutyAmount, 0) > 0
                  {date_filter}
                ORDER BY COALESCE(s.CertificateIssuedDate, d.TransactionDate), d.TransactionID
                """
            ),
            params,
        ).mappings().all()
        return [dict(row) for row in rows]

    def _shcil_wallet_opening_balance(
        self,
        *,
        manual_opening: dict[str, Any],
        account_id: int,
        as_of_date: date,
    ) -> Decimal:
        opening_balance = self._decimal_value(manual_opening["opening_balance"])
        opening_date = manual_opening["opening_balance_date"]
        if as_of_date <= opening_date:
            return opening_balance

        day_before = date.fromordinal(as_of_date.toordinal() - 1)
        deposits = self._shcil_wallet_deposits(
            account_id=account_id,
            start_date=opening_date,
            end_date=day_before,
        )
        stamps = self._shcil_stamp_prints(start_date=opening_date, end_date=day_before)
        deposit_total = sum(self._decimal_value(row["DepositAmount"]) for row in deposits)
        stamp_total = sum(self._decimal_value(row["StampUsed"]) for row in stamps)
        return opening_balance + deposit_total - stamp_total

    def _build_shcil_wallet_ledger(
        self,
        *,
        manual_opening: dict[str, Any],
        opening_at_start: Decimal,
        deposits: list[dict[str, Any]],
        stamps: list[dict[str, Any]],
        period_start: date,
        period_end: date,
    ) -> list[dict[str, Any]]:
        opening_date = manual_opening["opening_balance_date"]
        manual_amount = self._decimal_value(manual_opening["opening_balance"])
        ledger: list[dict[str, Any]] = []

        if period_start <= opening_date <= period_end:
            ledger.append(
                {
                    "TransactionDate": opening_date,
                    "Particular": "Opening Balance",
                    "Deposit": None,
                    "StampUsed": None,
                    "WalletBalance": manual_amount,
                }
            )
            event_start = opening_date
            running_balance = manual_amount
        else:
            ledger.append(
                {
                    "TransactionDate": period_start,
                    "Particular": "Opening Balance",
                    "Deposit": None,
                    "StampUsed": None,
                    "WalletBalance": opening_at_start,
                }
            )
            event_start = period_start
            running_balance = opening_at_start

        events: list[tuple[date, int, int, str, Decimal | None, Decimal | None]] = []
        for index, row in enumerate(deposits):
            event_date = row["TransactionDate"]
            if event_date < event_start or event_date > period_end:
                continue
            if period_start <= opening_date <= period_end and event_date == opening_date:
                sort_order = 0
            else:
                sort_order = 0
            amount = self._decimal_value(row["DepositAmount"])
            description = (row.get("Description") or "Deposit").strip()
            events.append((event_date, sort_order, index, description, amount, None))

        for index, row in enumerate(stamps):
            event_date = row["EventDate"]
            if event_date < event_start or event_date > period_end:
                continue
            amount = self._decimal_value(row["StampUsed"])
            certificate = (row.get("CertificateNumber") or "Stamp Print").strip()
            sort_order = 1
            if period_start <= opening_date <= period_end and event_date == opening_date:
                sort_order = 2
            events.append(
                (
                    event_date,
                    sort_order,
                    index,
                    f"Stamp Print - {certificate}",
                    None,
                    amount,
                )
            )

        events.sort(key=lambda item: (item[0], item[1], item[2]))
        balance = running_balance
        for event_date, _, _, particular, deposit_amount, stamp_amount in events:
            if deposit_amount is not None:
                balance += deposit_amount
            if stamp_amount is not None:
                balance -= stamp_amount
            ledger.append(
                {
                    "TransactionDate": event_date,
                    "Particular": particular,
                    "Deposit": deposit_amount,
                    "StampUsed": stamp_amount,
                    "WalletBalance": balance,
                }
            )
        return ledger

    def stamp_collection(self, filters: ReportFilters) -> dict[str, Any]:
        account = self._shcil_wallet_account()
        if account is None:
            raise ValueError(
                f"SHCIL wallet account {self.SHCIL_WALLET_ACCOUNT} not found in bank master."
            )

        manual_opening = self.get_shcil_opening_balance()
        if manual_opening is None:
            manual_opening = {
                "opening_balance": Decimal("0"),
                "opening_balance_date": filters.start_date,
                "updated_by": None,
                "updated_date": None,
            }

        opening_date = manual_opening["opening_balance_date"]
        opening_at_start = self._shcil_wallet_opening_balance(
            manual_opening=manual_opening,
            account_id=int(account["JtcsBankAccountID"]),
            as_of_date=filters.start_date,
        )
        period_deposits = self._shcil_wallet_deposits(
            account_id=int(account["JtcsBankAccountID"]),
            start_date=filters.start_date,
            end_date=filters.end_date,
        )
        period_stamps = self._shcil_stamp_prints(
            start_date=filters.start_date,
            end_date=filters.end_date,
        )
        total_deposit = sum(self._decimal_value(row["DepositAmount"]) for row in period_deposits)
        total_stamp_printed = sum(self._decimal_value(row["StampUsed"]) for row in period_stamps)
        available_balance = opening_at_start + total_deposit
        current_balance = available_balance - total_stamp_printed

        lifetime_deposits = self._shcil_wallet_deposits(
            account_id=int(account["JtcsBankAccountID"]),
            start_date=opening_date,
            end_date=filters.end_date,
        )
        lifetime_stamps = self._shcil_stamp_prints(
            start_date=opening_date,
            end_date=filters.end_date,
        )
        lifetime_deposit_total = sum(
            self._decimal_value(row["DepositAmount"]) for row in lifetime_deposits
        )
        lifetime_stamp_total = sum(self._decimal_value(row["StampUsed"]) for row in lifetime_stamps)
        manual_opening_amount = self._decimal_value(manual_opening["opening_balance"])
        lifetime_available = manual_opening_amount + lifetime_deposit_total
        lifetime_current_balance = lifetime_available - lifetime_stamp_total

        rows = self._build_shcil_wallet_ledger(
            manual_opening=manual_opening,
            opening_at_start=opening_at_start,
            deposits=period_deposits,
            stamps=period_stamps,
            period_start=filters.start_date,
            period_end=filters.end_date,
        )

        return {
            "title": self.REPORTS["stamp-collection"],
            "rows": rows,
            "total": current_balance,
            "summary": {
                "shcil_account": self.SHCIL_WALLET_ACCOUNT,
                "bank_name": account.get("BankName"),
                "opening_balance": opening_at_start,
                "total_deposit": total_deposit,
                "available_balance": available_balance,
                "total_stamp_printed": total_stamp_printed,
                "current_balance": current_balance,
                "manual_opening_balance": manual_opening_amount,
                "manual_opening_balance_date": opening_date,
                "manual_opening_saved": manual_opening.get("updated_by") is not None,
                "updated_by": manual_opening.get("updated_by"),
                "lifetime_total_deposit": lifetime_deposit_total,
                "lifetime_available_balance": lifetime_available,
                "lifetime_total_stamp_printed": lifetime_stamp_total,
                "lifetime_current_balance": lifetime_current_balance,
            },
            "opening_form": {
                "opening_balance": str(manual_opening_amount),
                "opening_balance_date": opening_date.isoformat(),
            },
        }

    def stamp_customer_wise(self, filters: ReportFilters) -> dict[str, Any]:
        params = {"start_date": filters.start_date, "end_date": filters.end_date}
        customer_filter = ""
        if filters.customer_id:
            customer_filter = "AND d.CustomerID = :customer_id"
            params["customer_id"] = filters.customer_id

        rows = db.session.execute(
            text(
                f"""
                SELECT d.CustomerID,
                       ISNULL(d.CustomerName, N'Walk-in') AS CustomerName,
                       COUNT(*) AS StampCount,
                       ISNULL(SUM(d.SaleAmount), 0) AS TotalSaleAmount
                FROM JTCSDailyTransaction d
                WHERE d.TransactionDate BETWEEN :start_date AND :end_date
                  AND d.Status = N'Posted'
                  {self.STAMP_FILTER}
                  {customer_filter}
                GROUP BY d.CustomerID, d.CustomerName
                ORDER BY CustomerName
                """
            ),
            params,
        ).mappings().all()
        total = sum(Decimal(str(row["TotalSaleAmount"] or 0)) for row in rows)
        return {"title": self.REPORTS["stamp-customer-wise"], "rows": rows, "total": total}

    def stamp_date_wise(self, filters: ReportFilters) -> dict[str, Any]:
        rows = db.session.execute(
            text(
                f"""
                SELECT d.TransactionDate,
                       COUNT(*) AS StampCount,
                       ISNULL(SUM(d.SaleAmount), 0) AS TotalSaleAmount
                FROM JTCSDailyTransaction d
                WHERE d.TransactionDate BETWEEN :start_date AND :end_date
                  AND d.Status = N'Posted'
                  {self.STAMP_FILTER}
                GROUP BY d.TransactionDate
                ORDER BY d.TransactionDate
                """
            ),
            {"start_date": filters.start_date, "end_date": filters.end_date},
        ).mappings().all()
        total = sum(Decimal(str(row["TotalSaleAmount"] or 0)) for row in rows)
        return {"title": self.REPORTS["stamp-date-wise"], "rows": rows, "total": total}

    def stamp_payment_mode(self, filters: ReportFilters) -> dict[str, Any]:
        rows = db.session.execute(
            text(
                f"""
                SELECT pm.PaymentModeName,
                       COUNT(d.TransactionID) AS StampCount,
                       ISNULL(SUM(d.SaleAmount), 0) AS TotalSaleAmount
                FROM JTCSDailyTransaction d
                LEFT JOIN PaymentModeMaster pm ON pm.PaymentModeID = d.PaymentModeID
                WHERE d.TransactionDate BETWEEN :start_date AND :end_date
                  AND d.Status = N'Posted'
                  {self.STAMP_FILTER}
                GROUP BY pm.PaymentModeName
                ORDER BY pm.PaymentModeName
                """
            ),
            {"start_date": filters.start_date, "end_date": filters.end_date},
        ).mappings().all()
        total = sum(Decimal(str(row["TotalSaleAmount"] or 0)) for row in rows)
        return {"title": self.REPORTS["stamp-payment-mode"], "rows": rows, "total": total}

    def stamp_certificate_wise(self, filters: ReportFilters) -> dict[str, Any]:
        rows = db.session.execute(
            text(
                f"""
                SELECT s.CertificateNumber,
                       s.CertificateIssuedDate,
                       d.TransactionDate,
                       d.CustomerName,
                       d.SaleAmount,
                       pm.PaymentModeName,
                       d.TransactionID,
                       s.StampID
                FROM StampMaster s
                INNER JOIN JTCSDailyTransaction d ON d.StampID = s.StampID
                LEFT JOIN PaymentModeMaster pm ON pm.PaymentModeID = d.PaymentModeID
                WHERE d.TransactionDate BETWEEN :start_date AND :end_date
                  AND d.Status = N'Posted'
                  {self.STAMP_FILTER}
                ORDER BY s.CertificateNumber
                """
            ),
            {"start_date": filters.start_date, "end_date": filters.end_date},
        ).mappings().all()
        total = sum(Decimal(str(row["SaleAmount"] or 0)) for row in rows)
        return {"title": self.REPORTS["stamp-certificate-wise"], "rows": rows, "total": total}
