from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.shcil_wallet import ShcilWalletOpeningBalance


class ShcilWalletOpeningRepository:
    def __init__(self, session: Session | None = None):
        self.session = session or db.session
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        self.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.ShcilWalletOpeningBalance', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.ShcilWalletOpeningBalance (
                        OpeningID           INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
                        AccountNumber       NVARCHAR(50) NOT NULL,
                        OpeningBalance      DECIMAL(18, 2) NOT NULL
                            CONSTRAINT DF_ShcilWalletOpeningBalance_OpeningBalance DEFAULT (0),
                        OpeningBalanceDate  DATE NOT NULL,
                        UpdatedBy           NVARCHAR(150) NOT NULL,
                        UpdatedDate         DATETIME2 NOT NULL
                            CONSTRAINT DF_ShcilWalletOpeningBalance_UpdatedDate DEFAULT (SYSUTCDATETIME()),
                        CONSTRAINT UX_ShcilWalletOpeningBalance_AccountNumber UNIQUE (AccountNumber)
                    );
                END
                """
            )
        )
        self._schema_ready = True

    def get_by_account(self, account_number: str) -> ShcilWalletOpeningBalance | None:
        self.ensure_schema()
        stmt = (
            select(ShcilWalletOpeningBalance)
            .where(ShcilWalletOpeningBalance.AccountNumber == account_number)
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def save(
        self,
        *,
        account_number: str,
        opening_balance: Decimal,
        opening_balance_date: date,
        updated_by: str,
    ) -> ShcilWalletOpeningBalance:
        self.ensure_schema()
        existing = self.get_by_account(account_number)
        now = datetime.utcnow()
        if existing is None:
            row = ShcilWalletOpeningBalance(
                AccountNumber=account_number,
                OpeningBalance=opening_balance,
                OpeningBalanceDate=opening_balance_date,
                UpdatedBy=updated_by,
                UpdatedDate=now,
            )
            self.session.add(row)
            self.session.flush()
            return row

        existing.OpeningBalance = opening_balance
        existing.OpeningBalanceDate = opening_balance_date
        existing.UpdatedBy = updated_by
        existing.UpdatedDate = now
        self.session.flush()
        return existing
