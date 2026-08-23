from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Numeric, Unicode
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class WebsiteEStampOrder(db.Model):
    __tablename__ = "WebsiteEStampOrder"

    OrderID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ReferenceNo: Mapped[str] = mapped_column(Unicode(40), nullable=False, unique=True)
    FullName: Mapped[str] = mapped_column(Unicode(160), nullable=False)
    FatherOrHusbandName: Mapped[str | None] = mapped_column(Unicode(160), nullable=True)
    SecondPartyName: Mapped[str | None] = mapped_column(Unicode(160), nullable=True)
    SecondPartyFatherOrHusbandName: Mapped[str | None] = mapped_column(Unicode(160), nullable=True)
    Mobile: Mapped[str] = mapped_column(Unicode(15), nullable=False)
    ConsiderationPrice: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    Description: Mapped[str | None] = mapped_column(Unicode(50), nullable=True)
    PoiDocumentType: Mapped[str | None] = mapped_column(Unicode(40), nullable=True)
    PoiDocPath: Mapped[str | None] = mapped_column(Unicode(400), nullable=True)
    PoiDocName: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    ArticleCode: Mapped[str] = mapped_column(Unicode(40), nullable=False)
    ArticleLabel: Mapped[str | None] = mapped_column(Unicode(240), nullable=True)
    Amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    PayableAmount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    DeliveryMode: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    HouseNo: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    Gali: Mapped[str | None] = mapped_column(Unicode(160), nullable=True)
    Mohalla: Mapped[str | None] = mapped_column(Unicode(160), nullable=True)
    Landmark: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    AddressNote: Mapped[str | None] = mapped_column(Unicode(300), nullable=True)
    GeoAddress: Mapped[str | None] = mapped_column(Unicode(400), nullable=True)
    LocationUrl: Mapped[str | None] = mapped_column(Unicode(500), nullable=True)
    PayMethod: Mapped[str | None] = mapped_column(Unicode(40), nullable=True)
    UtrNumber: Mapped[str | None] = mapped_column(Unicode(40), nullable=True)
    PaymentStatus: Mapped[str] = mapped_column(Unicode(30), nullable=False, default="paid")
    IsPaid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    ReviewStatus: Mapped[str] = mapped_column(Unicode(40), nullable=False, default="New")
    ReviewNotes: Mapped[str | None] = mapped_column(Unicode(500), nullable=True)
    CustomerID: Mapped[int | None] = mapped_column(Integer, nullable=True)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    ModifiedDate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
