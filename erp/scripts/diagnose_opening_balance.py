"""Read-only diagnostic: Bank Master OB vs Dashboard period opening for all accounts."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app import create_app
from app.extensions import db
from sqlalchemy import text


def money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def main() -> None:
    app = create_app()
    fy_from = date(2026, 4, 1)
    with app.app_context():
        print("=== BANK MASTER ALL ACCOUNTS ===")
        masters = db.session.execute(
            text(
                """
                SELECT JtcsBankAccountID, BankName, AccountNumber, ActiveStatus,
                       OpeningBalance, OpeningBalanceDate, OpeningBalanceDrCr
                FROM JtcsBankAccountMaster
                ORDER BY CASE WHEN BankName = N'Cash' THEN 0 ELSE 1 END, BankName
                """
            )
        ).mappings().all()
        for row in masters:
            print(dict(row))

        print(f"\n=== CASH MASTER SUM as of {fy_from} ===")
        master_ob = db.session.execute(
            text(
                """
                SELECT ISNULL(SUM(ISNULL(OpeningBalance, 0)), 0)
                FROM JtcsBankAccountMaster
                WHERE BankName = N'Cash'
                  AND (OpeningBalanceDate IS NULL OR OpeningBalanceDate <= :d)
                """
            ),
            {"d": fy_from},
        ).scalar()
        print(master_ob)

        print(f"\n=== CASH PRIOR NET before {fy_from} ===")
        prior_net = db.session.execute(
            text(
                """
                SELECT ISNULL(SUM(ISNULL(Debit, 0)), 0) - ISNULL(SUM(ISNULL(Credit, 0)), 0)
                FROM JtcsBankTransaction
                WHERE BankName = N'Cash' AND TransactionDate < :d
                """
            ),
            {"d": fy_from},
        ).scalar()
        print(prior_net)

        print("\n=== CASH TXNS BEFORE PERIOD ===")
        rows = db.session.execute(
            text(
                """
                SELECT JtcsBankTransactionID, TransactionDate, Description, Debit, Credit,
                       SourceTable, SourceType, SourceRecordID, BankName
                FROM JtcsBankTransaction
                WHERE BankName = N'Cash' AND TransactionDate < :d
                ORDER BY TransactionDate, JtcsBankTransactionID
                """
            ),
            {"d": fy_from},
        ).mappings().all()
        for row in rows:
            print(dict(row))
        print("count", len(rows))

        print("\n=== PER-ACCOUNT COMPARISON ===")
        print(
            "BankName | MasterOB | PriorNet(<period) | DashboardPeriodOpening | Diff | OBDate"
        )
        cmp_rows = db.session.execute(
            text(
                """
                SELECT
                    m.JtcsBankAccountID,
                    m.BankName,
                    m.AccountNumber,
                    m.ActiveStatus,
                    ISNULL(m.OpeningBalance, 0) AS master_ob,
                    m.OpeningBalanceDate,
                    ISNULL((
                        SELECT SUM(ISNULL(t.Debit, 0)) - SUM(ISNULL(t.Credit, 0))
                        FROM JtcsBankTransaction t
                        WHERE t.BankName = m.BankName
                          AND t.TransactionDate < :d
                    ), 0) AS prior_net
                FROM JtcsBankAccountMaster m
                ORDER BY CASE WHEN m.BankName = N'Cash' THEN 0 ELSE 1 END, m.BankName
                """
            ),
            {"d": fy_from},
        ).mappings().all()

        mismatches = []
        for row in cmp_rows:
            master = money(row["master_ob"])
            prior = money(row["prior_net"])
            dashboard = master + prior
            diff = dashboard - master
            line = (
                f"{row['BankName']} | {master} | {prior} | {dashboard} | {diff} | "
                f"{row['OpeningBalanceDate']}"
            )
            print(line)
            if diff != 0:
                mismatches.append(line)

        print("\n=== MISMATCHES (Diff != 0) ===")
        if mismatches:
            for line in mismatches:
                print(line)
        else:
            print("None")

        # Also compare via DashboardService methods
        from app.services.dashboard_service import DashboardService

        svc = DashboardService()
        cash_master = svc._master_opening_balance(cash_only=True, as_of=fy_from)
        cash_prior = svc._ledger_txn_net(cash_only=True, before=fy_from)
        cash_period = svc._ledger_opening_balance(cash_only=True, date_from=fy_from)
        print("\n=== DashboardService Cash ===")
        print("master", cash_master, "prior", cash_prior, "period_opening", cash_period)

        bank_master = svc._master_opening_balance(cash_only=False, as_of=fy_from)
        bank_prior = svc._ledger_txn_net(cash_only=False, before=fy_from)
        bank_period = svc._ledger_opening_balance(cash_only=False, date_from=fy_from)
        print("=== DashboardService Bank (all non-cash) ===")
        print("master", bank_master, "prior", bank_prior, "period_opening", bank_period)

        print("\n=== AFTER-FIX VERIFICATION (DashboardService) ===")
        print(
            "Cash master OB vs period opening:",
            cash_master,
            cash_period,
            "MATCH" if cash_master == cash_period else "MISMATCH",
        )

        print("\n=== PER-ACCOUNT: Master OB vs Dashboard period opening (post-fix rule) ===")
        fixed_rows = db.session.execute(
            text(
                """
                SELECT
                    m.BankName,
                    m.AccountNumber,
                    ISNULL(m.OpeningBalance, 0) AS master_ob,
                    m.OpeningBalanceDate,
                    ISNULL((
                        SELECT SUM(ISNULL(t.Debit, 0)) - SUM(ISNULL(t.Credit, 0))
                        FROM JtcsBankTransaction t
                        WHERE t.JtcsBankAccountID = m.JtcsBankAccountID
                          AND t.TransactionDate < :d
                          AND (
                                m.OpeningBalanceDate IS NULL
                                OR t.TransactionDate >= m.OpeningBalanceDate
                              )
                    ), 0) AS prior_net_post_ob
                FROM JtcsBankAccountMaster m
                ORDER BY CASE WHEN m.BankName = N'Cash' THEN 0 ELSE 1 END, m.BankName
                """
            ),
            {"d": fy_from},
        ).mappings().all()
        all_match = True
        for row in fixed_rows:
            master = money(row["master_ob"])
            prior = money(row["prior_net_post_ob"])
            dashboard = master + prior
            diff = dashboard - master
            status = "OK" if diff == 0 else "DIFF"
            if diff != 0:
                all_match = False
            print(
                f"{row['BankName']} | {row['AccountNumber']} | master={master} "
                f"| dash_open={dashboard} | diff={diff} | {status}"
            )
        print("ALL_ACCOUNTS_MATCH" if all_match else "SOME_MISMATCHES_REMAIN")


if __name__ == "__main__":
    main()
