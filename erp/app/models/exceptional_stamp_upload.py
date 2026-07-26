from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Integer, Unicode, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


class ExceptionalStampUploadBatch(db.Model):
    __tablename__ = "ExceptionalStampUploadBatch"

    BatchID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    SourceFileName: Mapped[str | None] = mapped_column(Unicode(260), nullable=True)
    ReportDateFrom: Mapped[date | None] = mapped_column(Date, nullable=True)
    ReportDateTo: Mapped[date | None] = mapped_column(Date, nullable=True)
    UploadedBy: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    UploadedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    TotalRows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    NewRows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    SkippedRows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    certificates: Mapped[list["ExceptionalStampUploadCertificate"]] = relationship(
        "ExceptionalStampUploadCertificate",
        back_populates="batch",
    )


class ExceptionalStampUploadCertificate(db.Model):
    __tablename__ = "ExceptionalStampUploadCertificate"

    UploadID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    BatchID: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("ExceptionalStampUploadBatch.BatchID"),
        nullable=True,
    )
    CertificateNumber: Mapped[str] = mapped_column(Unicode(100), nullable=False, unique=True)
    StampDutyAmount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    StampDutyType: Mapped[str | None] = mapped_column(Unicode(300), nullable=True)
    PaidBy: Mapped[str | None] = mapped_column(Unicode(300), nullable=True)
    SourceFileName: Mapped[str | None] = mapped_column(Unicode(260), nullable=True)
    ReportDateFrom: Mapped[date | None] = mapped_column(Date, nullable=True)
    ReportDateTo: Mapped[date | None] = mapped_column(Date, nullable=True)
    UploadedBy: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    UploadedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    LastSeenDate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    batch: Mapped[ExceptionalStampUploadBatch | None] = relationship(
        "ExceptionalStampUploadBatch",
        back_populates="certificates",
    )


class ExceptionalStampImport(db.Model):
    """Final reviewed SHCIL CSV rows saved via Final Import."""

    __tablename__ = "ExceptionalStampImport"

    ImportID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    BatchID: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("ExceptionalStampUploadBatch.BatchID"),
        nullable=True,
    )
    CertificateNumber: Mapped[str] = mapped_column(Unicode(100), nullable=False, unique=True)
    StampDutyAmount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    StampDutyType: Mapped[str | None] = mapped_column(Unicode(300), nullable=True)
    PaidBy: Mapped[str | None] = mapped_column(Unicode(300), nullable=True)
    CertificateStatus: Mapped[str | None] = mapped_column(Unicode(300), nullable=True)
    SourceFileName: Mapped[str | None] = mapped_column(Unicode(260), nullable=True)
    ReportDateFrom: Mapped[date | None] = mapped_column(Date, nullable=True)
    ReportDateTo: Mapped[date | None] = mapped_column(Date, nullable=True)
    ImportedBy: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    ImportedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
