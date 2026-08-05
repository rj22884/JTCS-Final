from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, Unicode
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class FixedAssetMaster(db.Model):
    __tablename__ = "FixedAssetMaster"

    AssetID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    AssetName: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    AccountID: Mapped[int | None] = mapped_column(Integer, nullable=True)
    GroupID: Mapped[int | None] = mapped_column(Integer, nullable=True)
    PurchaseDate: Mapped[date] = mapped_column(Date, nullable=False)
    PurchaseValue: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    DepreciationRate: Mapped[Decimal] = mapped_column(Numeric(9, 4), nullable=False, default=0)
    OpeningAccumulatedDep: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    CurrentYearDepreciation: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    AccumulatedDepreciation: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    WDV: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    Method: Mapped[str] = mapped_column(Unicode(20), nullable=False, default="WDV")
    IsActive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    UpdatedDate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
