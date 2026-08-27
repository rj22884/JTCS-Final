from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, Unicode
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


class WorkMaster(db.Model):
    __tablename__ = "WorkMaster"

    WorkID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    WorkName: Mapped[str] = mapped_column(Unicode(100), nullable=False)
    LedgerKind: Mapped[str] = mapped_column(Unicode(10), nullable=False)
    ChartGroupID: Mapped[int | None] = mapped_column(Integer, nullable=True)
    OpeningBalance: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    OpeningBalanceDate: Mapped[date | None] = mapped_column(Date, nullable=True)
    OpeningBalanceDrCr: Mapped[str | None] = mapped_column(Unicode(2), nullable=True)
    ActiveStatus: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    printing_entries: Mapped[list["PrintingScanMaster"]] = relationship(
        "PrintingScanMaster",
        back_populates="work_type",
    )


class PrintingScanMaster(db.Model):
    __tablename__ = "PrintingScanMaster"

    PrintingScanID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    BillNo: Mapped[str] = mapped_column(Unicode(50), nullable=False, unique=True)
    WorkDate: Mapped[date] = mapped_column(Date, nullable=False)
    WorkID: Mapped[int] = mapped_column(Integer, db.ForeignKey("WorkMaster.WorkID"), nullable=False)
    SaleAmount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    CustomerName: Mapped[str | None] = mapped_column(Unicode(255), nullable=True)
    MobileNumber: Mapped[str | None] = mapped_column(Unicode(15), nullable=True)
    Remarks: Mapped[str | None] = mapped_column(Unicode(500), nullable=True)
    CreatedBy: Mapped[str | None] = mapped_column(Unicode(100), nullable=True)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    IsActive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    work_type: Mapped["WorkMaster"] = relationship("WorkMaster", back_populates="printing_entries")


class OthersIncomeExpenseMaster(db.Model):
    __tablename__ = "OthersIncomeExpenseMaster"

    EntryID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    BillNo: Mapped[str] = mapped_column(Unicode(50), nullable=False, unique=True)
    WorkDate: Mapped[date] = mapped_column(Date, nullable=False)
    WorkID: Mapped[int] = mapped_column(Integer, db.ForeignKey("WorkMaster.WorkID"), nullable=False)
    Amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    CustomerName: Mapped[str | None] = mapped_column(Unicode(255), nullable=True)
    MobileNumber: Mapped[str | None] = mapped_column(Unicode(15), nullable=True)
    CustomerID: Mapped[int | None] = mapped_column(Integer, nullable=True)
    WorkDone: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    TallyBillGenerated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    TallyBillNo: Mapped[str | None] = mapped_column(Unicode(50), nullable=True)
    TallyBillDate: Mapped[date | None] = mapped_column(Date, nullable=True)
    TallyBillAmount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    Remarks: Mapped[str | None] = mapped_column(Unicode(500), nullable=True)
    CreatedBy: Mapped[str | None] = mapped_column(Unicode(100), nullable=True)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    IsActive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    work_type: Mapped["WorkMaster"] = relationship("WorkMaster")
    detail_lines: Mapped[list["OthersIncomeExpenseDetail"]] = relationship(
        "OthersIncomeExpenseDetail",
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="OthersIncomeExpenseDetail.LineSequence",
    )


class OthersIncomeExpenseDetail(db.Model):
    __tablename__ = "OthersIncomeExpenseDetail"

    DetailID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    EntryID: Mapped[int] = mapped_column(
        Integer, db.ForeignKey("OthersIncomeExpenseMaster.EntryID"), nullable=False
    )
    LineSequence: Mapped[int] = mapped_column(Integer, nullable=False)
    WorkID: Mapped[int] = mapped_column(Integer, db.ForeignKey("WorkMaster.WorkID"), nullable=False)
    WorkTypeID: Mapped[int | None] = mapped_column(
        Integer, db.ForeignKey("WorkTypeMaster.WorkTypeID"), nullable=True
    )
    Amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    entry: Mapped["OthersIncomeExpenseMaster"] = relationship(
        "OthersIncomeExpenseMaster",
        back_populates="detail_lines",
    )
    work_type: Mapped["WorkMaster"] = relationship("WorkMaster")
    sub_work_type: Mapped["WorkTypeMaster | None"] = relationship("WorkTypeMaster")
