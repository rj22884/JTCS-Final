from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, Unicode
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class ItemMaster(db.Model):
    __tablename__ = "ItemMaster"

    ItemID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ItemCode: Mapped[str] = mapped_column(Unicode(40), nullable=False)
    ItemName: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    Description: Mapped[str | None] = mapped_column(Unicode(500), nullable=True)
    HsnSac: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    HsnSacType: Mapped[str] = mapped_column(Unicode(10), nullable=False, default="SAC")
    Unit: Mapped[str] = mapped_column(Unicode(30), nullable=False, default="NOS")
    DefaultRate: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    GstApplicable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    GstRatePercent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=18)
    OpeningQty: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    OpeningRate: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    OpeningBalance: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    OpeningBalanceDate: Mapped[date | None] = mapped_column(Date, nullable=True)
    ChartGroupID: Mapped[int | None] = mapped_column(Integer, nullable=True)
    OrderNo: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    IsActive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    CreatedAt: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    UpdatedAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class GstInvoice(db.Model):
    __tablename__ = "GstInvoice"

    InvoiceID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    InvoiceNo: Mapped[str] = mapped_column(Unicode(40), nullable=False)
    InvoiceDate: Mapped[date] = mapped_column(Date, nullable=False)
    CustomerID: Mapped[int | None] = mapped_column(Integer, nullable=True)
    CustomerName: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    ContactPerson: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    BillingAddress: Mapped[str | None] = mapped_column(Unicode(500), nullable=True)
    CustomerGSTIN: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    ContactMobile: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    ContactEmail: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    PlaceOfSupply: Mapped[str | None] = mapped_column(Unicode(100), nullable=True)
    PlaceOfSupplyCode: Mapped[str | None] = mapped_column(Unicode(5), nullable=True)
    ReverseCharge: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    InvoiceKind: Mapped[str] = mapped_column(Unicode(20), nullable=False, default="NON_GST")
    VoucherType: Mapped[str] = mapped_column(Unicode(20), nullable=False, default="SALE")
    TaxType: Mapped[str] = mapped_column(Unicode(10), nullable=False, default="IGST")
    ListPrice: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    DiscountAmount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    TaxableValue: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    CgstRate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    CgstAmount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    SgstRate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    SgstAmount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    IgstRate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    IgstAmount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    InvoiceValue: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    RoundOffAmount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    AmountInWords: Mapped[str | None] = mapped_column(Unicode(500), nullable=True)
    Notes: Mapped[str | None] = mapped_column(Unicode(500), nullable=True)
    PaymentBankAccountID: Mapped[int | None] = mapped_column(Integer, nullable=True)
    PayBankName: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    PayAccountNumber: Mapped[str | None] = mapped_column(Unicode(50), nullable=True)
    PayIFSC: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    PayBranch: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    PayAccountHolder: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    PayAccountType: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    PayUpiId: Mapped[str | None] = mapped_column(Unicode(100), nullable=True)
    PaymentDate: Mapped[date | None] = mapped_column(Date, nullable=True)
    AmountPaid: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    TallyBillNo: Mapped[str | None] = mapped_column(Unicode(50), nullable=True)
    DailyTransactionID: Mapped[int | None] = mapped_column(Integer, nullable=True)
    CreatedBy: Mapped[str | None] = mapped_column(Unicode(100), nullable=True)
    CreatedAt: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    UpdatedAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class GstInvoiceLine(db.Model):
    __tablename__ = "GstInvoiceLine"

    LineID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    InvoiceID: Mapped[int] = mapped_column(Integer, nullable=False)
    SrNo: Mapped[int] = mapped_column(Integer, nullable=False)
    ItemID: Mapped[int | None] = mapped_column(Integer, nullable=True)
    Particulars: Mapped[str] = mapped_column(Unicode(300), nullable=False)
    TaxPeriod: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    Quarter: Mapped[str | None] = mapped_column(Unicode(40), nullable=True)
    Month: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    HsnSac: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    Unit: Mapped[str | None] = mapped_column(Unicode(30), nullable=True)
    Qty: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=1)
    Rate: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    DiscountAmount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    TaxableValue: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    GstRatePercent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
