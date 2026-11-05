from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, Unicode
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class FollowupEntryMaster(db.Model):
    __tablename__ = "FollowupEntryMaster"

    EntryID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ModuleCode: Mapped[str] = mapped_column(Unicode(10), nullable=False)
    WorkDate: Mapped[date] = mapped_column(Date, nullable=False)
    TaxPeriod: Mapped[str] = mapped_column(Unicode(20), nullable=False)
    GstMonth: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    CustomerID: Mapped[int] = mapped_column(Integer, db.ForeignKey("CustomerMaster.CustomerID"), nullable=False)
    BillingType: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    BillingCustomerID: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ReturnType: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    FormType: Mapped[str | None] = mapped_column(Unicode(30), nullable=True)
    Quarter: Mapped[str | None] = mapped_column(Unicode(10), nullable=True)
    ApplicationNumber: Mapped[str | None] = mapped_column(Unicode(50), nullable=True)
    DscType: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    DscClass: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    DscYear: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    Location: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    IntroducedBy: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    BillNo: Mapped[str | None] = mapped_column(Unicode(50), nullable=True)
    BillDate: Mapped[date | None] = mapped_column(Date, nullable=True)
    BillAmount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    ITRFiledDate: Mapped[date | None] = mapped_column(Date, nullable=True)
    ReturnFilingStatus: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    FilingDate: Mapped[date | None] = mapped_column(Date, nullable=True)
    PANNumber: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    Remarks: Mapped[str | None] = mapped_column(Unicode(500), nullable=True)
    ReasonForUnverified: Mapped[str | None] = mapped_column(Unicode(500), nullable=True)
    CreatedBy: Mapped[str | None] = mapped_column(Unicode(100), nullable=True)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    ModifiedDate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    IsActive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    TickDocumentsReceived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    TickReturnFiled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    TickInvoice: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    TickPaymentReceived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    TickApplicationReceived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    TickKYC: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    TickDownloadStatus: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    TickUnverified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
