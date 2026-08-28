"""
Heal duplicate Customer Debits created by Follow-up workflow rows.

When a GST Sale / Service Invoice already exists for a Tally Bill Number,
any "ITR Followup" / "GST Followup" / etc. SaleAmount is a duplicate
receivable. This script:

- Posts the invoice daily if it is missing
- Removes sale-only follow-up debit rows
- Zeros SaleAmount on follow-up receipt rows (keeps the Customer Credit)
- Does not delete legitimate receipts or GST invoice dailies
- Leaves historical follow-up sales alone when no invoice exists

Usage (from erp folder):
    .venv\\Scripts\\python.exe scripts\\reconcile_payment_received_duplicates.py
    python scripts/reconcile_payment_received_duplicates.py --commit
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile duplicate Follow-up sale debits.")
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Persist changes. Default is a dry run (rollback).",
    )
    args = parser.parse_args()

    from app import create_app
    from app.extensions import db
    from app.services.payment_accounting_service import PaymentAccountingService

    app = create_app()
    with app.app_context():
        totals = PaymentAccountingService().reconcile_all_followup_duplicates()
        print(
            f"Bills scanned: {totals.get('bills', 0)} | "
            f"Invoice dailies posted: {totals.get('invoices_posted', 0)} | "
            f"Follow-up sale rows removed: {totals.get('removed_followup_sales', 0)} | "
            f"SaleAmount cleared on receipts: {totals.get('cleared_sale_on_receipts', 0)}"
        )
        if args.commit:
            db.session.commit()
            print("Committed.")
        else:
            db.session.rollback()
            print("Dry run — rolled back. Re-run with --commit to persist.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
