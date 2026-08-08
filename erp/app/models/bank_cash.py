from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, Unicode
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class PurposeMaster(db.Model):
    __tablename__ = "PurposeMaster"

    PurposeID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    PurposeName: Mapped[str] = mapped_column(Unicode(200), nullable=False, unique=True)
    Description: Mapped[str | None] = mapped_column(Unicode(500), nullable=True)
    ActiveStatus: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    CreatedBy: Mapped[str | None] = mapped_column(Unicode(100), nullable=True)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    ModifiedDate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RdAccountMaster(db.Model):
    __tablename__ = "RdAccountMaster"

    RdAccountID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    RdName: Mapped[str] = mapped_column(Unicode(150), nullable=False)
    BankName: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    RdNumber: Mapped[str] = mapped_column(Unicode(50), nullable=False, unique=True)
    BankAccountID: Mapped[int | None] = mapped_column(
        Integer, db.ForeignKey("JtcsBankAccountMaster.JtcsBankAccountID"), nullable=True
    )
    OpeningDate: Mapped[date | None] = mapped_column(Date, nullable=True)
    MaturityDate: Mapped[date | None] = mapped_column(Date, nullable=True)
    InterestRate: Mapped[Decimal | None] = mapped_column(Numeric(9, 4), nullable=True)
    InstallmentAmount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    OpeningBalance: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    ActiveStatus: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    Remarks: Mapped[str | None] = mapped_column(Unicode(500), nullable=True)
    CreatedBy: Mapped[str | None] = mapped_column(Unicode(100), nullable=True)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    ModifiedDate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class OthersBankCashTransaction(db.Model):
    __tablename__ = "OthersBankCashTransaction"

    EntryID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    VoucherNo: Mapped[str] = mapped_column(Unicode(50), nullable=False, unique=True)
    WorkDate: Mapped[date] = mapped_column(Date, nullable=False)
    Purpose: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    CreditBankAccountID: Mapped[int | None] = mapped_column(
        Integer, db.ForeignKey("JtcsBankAccountMaster.JtcsBankAccountID"), nullable=True
    )
    DebitBankAccountID: Mapped[int | None] = mapped_column(
        Integer, db.ForeignKey("JtcsBankAccountMaster.JtcsBankAccountID"), nullable=True
    )
    CreditLedgerKey: Mapped[str | None] = mapped_column(Unicode(40), nullable=True)
    DebitLedgerKey: Mapped[str | None] = mapped_column(Unicode(40), nullable=True)
    Amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    Remarks: Mapped[str | None] = mapped_column(Unicode(500), nullable=True)
    OutBankTransactionID: Mapped[int | None] = mapped_column(Integer, nullable=True)
    InBankTransactionID: Mapped[int | None] = mapped_column(Integer, nullable=True)
    CreatedBy: Mapped[str | None] = mapped_column(Unicode(100), nullable=True)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    IsActive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
