from datetime import date, datetime

from decimal import Decimal



from sqlalchemy import Boolean, Date, DateTime, Integer, LargeBinary, Numeric, Unicode, UnicodeText

from sqlalchemy.orm import Mapped, mapped_column



from app.extensions import db





class StampMaster(db.Model):

    __tablename__ = "StampMaster"



    StampID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    CertificateNumber: Mapped[str] = mapped_column(Unicode(100), nullable=False, unique=True)

    CertificateIssuedDate: Mapped[date | None] = mapped_column(Date, nullable=True)

    AccountReference: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)

    UniqueDocumentReference: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)

    PurchasedBy: Mapped[str | None] = mapped_column(Unicode(300), nullable=True)

    DescriptionOfDocument: Mapped[str | None] = mapped_column(Unicode(1000), nullable=True)

    PropertyDescription: Mapped[str | None] = mapped_column(Unicode(1000), nullable=True)

    ConsiderationPrice: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    FirstPartyName: Mapped[str | None] = mapped_column(Unicode(300), nullable=True)

    SecondPartyName: Mapped[str | None] = mapped_column(Unicode(300), nullable=True)

    StampDutyPaidBy: Mapped[str | None] = mapped_column(Unicode(300), nullable=True)

    StampDutyAmount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    CreatedBy: Mapped[str] = mapped_column(Unicode(150), nullable=False)

    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    ModifiedBy: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)

    ModifiedDate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    IsActive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    Remarks: Mapped[str | None] = mapped_column(Unicode(500), nullable=True)

    MachineName: Mapped[str | None] = mapped_column(Unicode(100), nullable=True)

    IPAddress: Mapped[str | None] = mapped_column(Unicode(45), nullable=True)
    MobileNumber: Mapped[str | None] = mapped_column(Unicode(15), nullable=True)





class StampOcrImage(db.Model):

    __tablename__ = "StampOcrImage"



    OcrImageID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    StampID: Mapped[int | None] = mapped_column(Integer, nullable=True)

    OriginalImage: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    ImageHash: Mapped[str | None] = mapped_column(Unicode(64), nullable=True)

    OcrText: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)

    OcrConfidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)

    OcrProvider: Mapped[str | None] = mapped_column(Unicode(50), nullable=True)

    ImageSize: Mapped[int | None] = mapped_column(Integer, nullable=True)

    CreatedBy: Mapped[str] = mapped_column(Unicode(150), nullable=False)

    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False)


