from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, Unicode
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


class ChartOfAccountMaster(db.Model):
    __tablename__ = "ChartOfAccountMaster"

    AccountID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    AccountName: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    GroupID: Mapped[int] = mapped_column(
        Integer, ForeignKey("ChartOfGroupMaster.GroupID"), nullable=False
    )
    CustomerID: Mapped[int | None] = mapped_column(Integer, nullable=True)
    WorkID: Mapped[int | None] = mapped_column(Integer, nullable=True)
    OpeningBalance: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    OpeningBalanceDate: Mapped[date | None] = mapped_column(Date, nullable=True)
    OpeningBalanceDrCr: Mapped[str | None] = mapped_column(Unicode(2), nullable=True)
    IsActive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    UpdatedDate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    group = relationship("ChartOfGroupMaster", lazy="joined")
