"""Daily currency-note count under Dashboard Cash Closing Balance.

Does not change Cash Closing Balance or any ledger posting.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from app.extensions import db
from app.utils.timezone import now_app, today_app

DENOMS = (500, 200, 100, 50, 20, 10, 5, 2, 1)
COL = {
    500: "Note500",
    200: "Note200",
    100: "Note100",
    50: "Note50",
    20: "Note20",
    10: "Note10",
    5: "Note5",
    2: "Note2",
    1: "Note1",
}


def _int_count(value: Any) -> int:
    try:
        n = int(Decimal(str(value or 0)))
    except (TypeError, ValueError, ArithmeticError):
        return 0
    return max(0, n)


class CurrencyNotesService:
    def __init__(self) -> None:
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        db.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.CurrencyNotesClosing', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.CurrencyNotesClosing (
                        EntryID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
                        EntryDate DATE NOT NULL,
                        Note500 INT NOT NULL CONSTRAINT DF_CurrencyNotesClosing_Note500 DEFAULT (0),
                        Note200 INT NOT NULL CONSTRAINT DF_CurrencyNotesClosing_Note200 DEFAULT (0),
                        Note100 INT NOT NULL CONSTRAINT DF_CurrencyNotesClosing_Note100 DEFAULT (0),
                        Note50 INT NOT NULL CONSTRAINT DF_CurrencyNotesClosing_Note50 DEFAULT (0),
                        Note20 INT NOT NULL CONSTRAINT DF_CurrencyNotesClosing_Note20 DEFAULT (0),
                        Note10 INT NOT NULL CONSTRAINT DF_CurrencyNotesClosing_Note10 DEFAULT (0),
                        Note5 INT NOT NULL CONSTRAINT DF_CurrencyNotesClosing_Note5 DEFAULT (0),
                        Note2 INT NOT NULL CONSTRAINT DF_CurrencyNotesClosing_Note2 DEFAULT (0),
                        Note1 INT NOT NULL CONSTRAINT DF_CurrencyNotesClosing_Note1 DEFAULT (0),
                        TotalNotes INT NOT NULL CONSTRAINT DF_CurrencyNotesClosing_TotalNotes DEFAULT (0),
                        TotalAmount DECIMAL(18, 2) NOT NULL
                            CONSTRAINT DF_CurrencyNotesClosing_TotalAmount DEFAULT (0),
                        CreatedBy NVARCHAR(150) NULL,
                        CreatedDate DATETIME2 NOT NULL
                            CONSTRAINT DF_CurrencyNotesClosing_CreatedDate DEFAULT (SYSUTCDATETIME()),
                        ModifiedBy NVARCHAR(150) NULL,
                        ModifiedDate DATETIME2 NULL,
                        IsActive BIT NOT NULL
                            CONSTRAINT DF_CurrencyNotesClosing_IsActive DEFAULT (1)
                    );
                    CREATE UNIQUE INDEX UX_CurrencyNotesClosing_Date
                        ON dbo.CurrencyNotesClosing (EntryDate)
                        WHERE IsActive = 1;
                END
                """
            )
        )
        db.session.commit()
        self._schema_ready = True

    @staticmethod
    def empty_payload(entry_date: date) -> dict[str, Any]:
        lines = [
            {
                "denomination": d,
                "notes": 0,
                "amount": 0.0,
            }
            for d in DENOMS
        ]
        return {
            "entry_date": entry_date.isoformat(),
            "lines": lines,
            "total_notes": 0,
            "total_amount": 0.0,
            "entry_id": None,
        }

    def get_for_date(self, entry_date: date | None = None) -> dict[str, Any]:
        self.ensure_schema()
        day = entry_date or today_app()
        row = db.session.execute(
            text(
                """
                SELECT TOP 1
                    EntryID, EntryDate,
                    Note500, Note200, Note100, Note50, Note20, Note10, Note5, Note2, Note1,
                    TotalNotes, TotalAmount
                FROM dbo.CurrencyNotesClosing
                WHERE EntryDate = :d AND ISNULL(IsActive, 1) = 1
                ORDER BY EntryID DESC
                """
            ),
            {"d": day},
        ).mappings().first()
        if not row:
            return self.empty_payload(day)
        lines = []
        total_notes = 0
        total_amount = Decimal("0.00")
        for denom in DENOMS:
            notes = _int_count(row[COL[denom]])
            amount = Decimal(denom) * Decimal(notes)
            total_notes += notes
            total_amount += amount
            lines.append(
                {
                    "denomination": denom,
                    "notes": notes,
                    "amount": float(amount.quantize(Decimal("0.01"))),
                }
            )
        return {
            "entry_date": day.isoformat(),
            "lines": lines,
            "total_notes": total_notes,
            "total_amount": float(total_amount.quantize(Decimal("0.01"))),
            "entry_id": int(row["EntryID"]),
        }

    def save(
        self,
        *,
        entry_date: date | None,
        counts: dict[int, int],
        user_name: str | None,
    ) -> dict[str, Any]:
        self.ensure_schema()
        day = entry_date or today_app()
        note_vals = {d: _int_count(counts.get(d)) for d in DENOMS}
        total_notes = sum(note_vals.values())
        total_amount = sum(Decimal(d) * Decimal(note_vals[d]) for d in DENOMS)
        total_amount = total_amount.quantize(Decimal("0.01"))
        existing = db.session.execute(
            text(
                """
                SELECT TOP 1 EntryID
                FROM dbo.CurrencyNotesClosing
                WHERE EntryDate = :d AND ISNULL(IsActive, 1) = 1
                ORDER BY EntryID DESC
                """
            ),
            {"d": day},
        ).scalar()
        params = {
            "d": day,
            "n500": note_vals[500],
            "n200": note_vals[200],
            "n100": note_vals[100],
            "n50": note_vals[50],
            "n20": note_vals[20],
            "n10": note_vals[10],
            "n5": note_vals[5],
            "n2": note_vals[2],
            "n1": note_vals[1],
            "tn": total_notes,
            "ta": total_amount,
            "user": (user_name or "")[:150] or None,
            "now": now_app(),
        }
        if existing:
            db.session.execute(
                text(
                    """
                    UPDATE dbo.CurrencyNotesClosing
                    SET Note500 = :n500, Note200 = :n200, Note100 = :n100,
                        Note50 = :n50, Note20 = :n20, Note10 = :n10,
                        Note5 = :n5, Note2 = :n2, Note1 = :n1,
                        TotalNotes = :tn, TotalAmount = :ta,
                        ModifiedBy = :user, ModifiedDate = :now
                    WHERE EntryID = :id
                    """
                ),
                {**params, "id": int(existing)},
            )
        else:
            db.session.execute(
                text(
                    """
                    INSERT INTO dbo.CurrencyNotesClosing (
                        EntryDate, Note500, Note200, Note100, Note50, Note20,
                        Note10, Note5, Note2, Note1, TotalNotes, TotalAmount, CreatedBy
                    )
                    VALUES (
                        :d, :n500, :n200, :n100, :n50, :n20,
                        :n10, :n5, :n2, :n1, :tn, :ta, :user
                    )
                    """
                ),
                params,
            )
        db.session.commit()
        return self.get_for_date(day)
