from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Integer, Numeric, Unicode
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class ShcilWalletOpeningBalance(db.Model):
    __tablename__ = "ShcilWalletOpeningBalance"

    OpeningID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    AccountNumber: Mapped[str] = mapped_column(Unicode(50), nullable=False)
    OpeningBalance: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    OpeningBalanceDate: Mapped[date] = mapped_column(Date, nullable=False)
    UpdatedBy: Mapped[str] = mapped_column(Unicode(150), nullable=False)
    UpdatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False)
