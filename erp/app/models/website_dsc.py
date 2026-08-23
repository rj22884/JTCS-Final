from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Numeric, Unicode
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class WebsiteDscApplication(db.Model):
    __tablename__ = "WebsiteDscApplication"

    ApplicationID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ReferenceNo: Mapped[str] = mapped_column(Unicode(40), nullable=False, unique=True)
    DscType: Mapped[str] = mapped_column(Unicode(80), nullable=False)
    ValidityYears: Mapped[int] = mapped_column(Integer, nullable=False)
    ApplicantType: Mapped[str] = mapped_column(Unicode(20), nullable=False)
    FullName: Mapped[str] = mapped_column(Unicode(160), nullable=False)
    Pan: Mapped[str] = mapped_column(Unicode(10), nullable=False)
    AadhaarLast4: Mapped[str | None] = mapped_column(Unicode(4), nullable=True)
    Mobile: Mapped[str] = mapped_column(Unicode(15), nullable=False)
    Email: Mapped[str] = mapped_column(Unicode(160), nullable=False)
    Address: Mapped[str] = mapped_column(Unicode(400), nullable=False)
    OrganizationName: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    OrganizationId: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    OrganizationAddress: Mapped[str | None] = mapped_column(Unicode(400), nullable=True)
    PanDocPath: Mapped[str | None] = mapped_column(Unicode(400), nullable=True)
    PanDocName: Mapped[str | None] = mapped_column(Unicode(180), nullable=True)
    AadhaarDocPath: Mapped[str | None] = mapped_column(Unicode(400), nullable=True)
    AadhaarDocName: Mapped[str | None] = mapped_column(Unicode(180), nullable=True)
    OrgIdDocPath: Mapped[str | None] = mapped_column(Unicode(400), nullable=True)
    OrgIdDocName: Mapped[str | None] = mapped_column(Unicode(180), nullable=True)
    AuthLetterPath: Mapped[str | None] = mapped_column(Unicode(400), nullable=True)
    AuthLetterName: Mapped[str | None] = mapped_column(Unicode(180), nullable=True)
    Amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, default=500)
    PayableAmount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    PayMethod: Mapped[str | None] = mapped_column(Unicode(40), nullable=True)
    UtrNumber: Mapped[str | None] = mapped_column(Unicode(40), nullable=True)
    PaymentStatus: Mapped[str] = mapped_column(Unicode(30), nullable=False, default="pending")
    IsPaid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ReviewStatus: Mapped[str] = mapped_column(Unicode(40), nullable=False, default="New")
    CustomerID: Mapped[int | None] = mapped_column(Integer, nullable=True)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    ModifiedDate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
