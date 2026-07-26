from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, Unicode
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


class ECourtReceiptBatch(db.Model):
    __tablename__ = "ECourtReceiptBatch"

    ImportID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    FileName: Mapped[str | None] = mapped_column(Unicode(260), nullable=True)
    ReportFrom: Mapped[date | None] = mapped_column(Date, nullable=True)
    ReportTo: Mapped[date | None] = mapped_column(Date, nullable=True)
    StateName: Mapped[str | None] = mapped_column(Unicode(100), nullable=True)
    TotalAmount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    RecordCount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ImportedBy: Mapped[str | None] = mapped_column(Unicode(100), nullable=True)
    ImportedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    lines: Mapped[list["ECourtReceiptLine"]] = relationship(
        "ECourtReceiptLine",
        back_populates="batch",
        cascade="all, delete-orphan",
    )


class ECourtReceiptLine(db.Model):
    __tablename__ = "ECourtReceiptLine"

    LineID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ImportID: Mapped[int] = mapped_column(Integer, ForeignKey("ECourtReceiptBatch.ImportID"), nullable=False)
    ReceiptNo: Mapped[str] = mapped_column(Unicode(50), nullable=False)
    ReceiptDate: Mapped[date | None] = mapped_column(Date, nullable=True)
    Amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    PaymentMode: Mapped[str | None] = mapped_column(Unicode(50), nullable=True)
    ReceiptStatus: Mapped[str | None] = mapped_column(Unicode(100), nullable=True)
    Remarks: Mapped[str | None] = mapped_column(Unicode(500), nullable=True)
    StationeryNumber: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)

    batch: Mapped["ECourtReceiptBatch"] = relationship("ECourtReceiptBatch", back_populates="lines")


class ECourtSale(db.Model):
    __tablename__ = "ECourtSale"

    SaleID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ReceiptNo: Mapped[str] = mapped_column(Unicode(50), nullable=False, unique=True)
    StationeryNumber: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    ReceiptDate: Mapped[date | None] = mapped_column(Date, nullable=True)
    Amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    CustomerName: Mapped[str | None] = mapped_column(Unicode(255), nullable=True)
    MobileNumber: Mapped[str | None] = mapped_column(Unicode(15), nullable=True)
    Remarks: Mapped[str | None] = mapped_column(Unicode(500), nullable=True)
    DailyTransactionID: Mapped[int | None] = mapped_column(Integer, nullable=True)
    CreatedBy: Mapped[str | None] = mapped_column(Unicode(100), nullable=True)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
