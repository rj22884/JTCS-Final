"""Apply e-Court migrations and run PDF parse/import smoke test."""

from __future__ import annotations



import sys

from pathlib import Path



ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(ROOT))



from app import create_app

from app.extensions import db

from app.services.ecourt_service import ECourtService

from sqlalchemy import text



MIGRATIONS = [

    ROOT / "database" / "018_ecourt_activity.sql",

    ROOT / "database" / "019_ecourt_stationery_number.sql",

    ROOT / "database" / "020_ecourt_receipt_stationery_unique.sql",

    ROOT / "database" / "021_ecourt_sale_daily_transaction.sql",

    ROOT / "database" / "022_ecourt_receipt_no_unique.sql",

]

SAMPLE_PDF = Path(r"C:\Users\USER\Downloads\05202644074441.pdf")





def run_migration(path: Path) -> None:

    sql = path.read_text(encoding="utf-8")

    for batch in sql.split("GO"):

        batch = batch.strip()

        if not batch or batch.upper().startswith("USE "):

            continue

        if batch.startswith("/*") or batch.startswith("PRINT"):

            continue

        db.session.execute(text(batch))

    db.session.commit()





def main() -> int:

    app = create_app()

    with app.app_context():

        for migration in MIGRATIONS:

            if migration.exists():

                run_migration(migration)

                print(f"OK  Applied {migration.name}")



        if not SAMPLE_PDF.exists():

            print(f"SKIP PDF test — file not found: {SAMPLE_PDF}")

            return 0



        raw = SAMPLE_PDF.read_bytes()

        service = ECourtService()

        preview = service.parse_pdf_preview(raw, file_name=SAMPLE_PDF.name)

        print(f"OK  Parsed {preview['record_count']} rows from PDF (preview)")



        result = service.import_rows(

            {

                "file_name": preview["file_name"],

                "report_from": preview["report_from"],

                "report_to": preview["report_to"],

                "state_name": preview["state_name"],

                "total_amount": preview["total_amount"],

                "rows": preview["rows"],

            },

            imported_by="ecourt.test",

        )

        db.session.commit()

        print(f"OK  Imported {result['record_count']} receipts (import #{result['import_id']})")



        search = service.search_stationery("2654", import_id=result["import_id"])

        print(

            f"OK  Stationery 2654: {search['summary_status']} "

            f"({search['sold_count']}/{search['total_receipts']} sold)"

        )



        try:
            sale = service.save_manual_sale(
                {
                    "ReceiptNo": "UKCT1758885D2654K",
                    "Amount": "10",
                    "ReceiptDate": "2026-04-17",
                    "CustomerName": "test",
                },
                created_by="ecourt.test",
            )
            db.session.commit()
            print(f"OK  Manual sale: {sale['message']}")
        except ValueError as exc:
            if "already marked as sold" not in str(exc):
                raise
            print(f"OK  Manual sale skipped: {exc}")



        search2 = service.search_stationery("2654", import_id=result["import_id"])

        print(

            f"OK  After sale stationery 2654: {search2['summary_status']} "

            f"({search2['sold_count']}/{search2['total_receipts']} sold)"

        )

    return 0





if __name__ == "__main__":

    raise SystemExit(main())

