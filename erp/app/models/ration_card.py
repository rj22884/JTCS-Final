from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Unicode
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class RationDealerMaster(db.Model):
    __tablename__ = "RationDealerMaster"

    DealerID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    DealerName: Mapped[str] = mapped_column(Unicode(200), nullable=False, unique=True)
    FPSID: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    ExistingFPSID: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    DistrictName: Mapped[str | None] = mapped_column(Unicode(120), nullable=True)
    TehsilName: Mapped[str | None] = mapped_column(Unicode(120), nullable=True)
    MobileNumber: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    Address: Mapped[str | None] = mapped_column(Unicode(400), nullable=True)
    ActiveStatus: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    CreatedBy: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ModifiedBy: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    ModifiedDate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RationCardUploadBatch(db.Model):
    __tablename__ = "RationCardUploadBatch"

    BatchID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    DealerID: Mapped[int] = mapped_column(
        Integer, ForeignKey("RationDealerMaster.DealerID"), nullable=False
    )
    SourceFileName: Mapped[str | None] = mapped_column(Unicode(260), nullable=True)
    FPSID: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    UploadedBy: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    UploadedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    TotalRows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    CardCount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    MemberCount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ImportMode: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)


class RationCardMember(db.Model):
    __tablename__ = "RationCardMember"

    MemberRowID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    BatchID: Mapped[int] = mapped_column(
        Integer, ForeignKey("RationCardUploadBatch.BatchID"), nullable=False
    )
    DealerID: Mapped[int] = mapped_column(
        Integer, ForeignKey("RationDealerMaster.DealerID"), nullable=False
    )
    RowNumber: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    DistrictName: Mapped[str | None] = mapped_column(Unicode(120), nullable=True)
    TehsilName: Mapped[str | None] = mapped_column(Unicode(120), nullable=True)
    SchemeName: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    ExistingFPSID: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    FPSID: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    RCNumber: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    ExistingRCNumber: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    MemberID: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    ExistingMemberID: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    FullName: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    FatherName: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    MotherName: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    Gender: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    MobileNumber: Mapped[str | None] = mapped_column(Unicode(30), nullable=True)
    Age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    IsHOF: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    Ekyc: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    UIDStatus: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    ChangeStatus: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    ChangeDetail: Mapped[str | None] = mapped_column(Unicode(800), nullable=True)


class PdsStateMaster(db.Model):
    __tablename__ = "PdsStateMaster"

    StateID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    StateCode: Mapped[str] = mapped_column(Unicode(10), nullable=False, unique=True)
    StateName: Mapped[str] = mapped_column(Unicode(120), nullable=False)
    Source: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    ActiveStatus: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    CreatedBy: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ModifiedBy: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    ModifiedDate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PdsDistrictMaster(db.Model):
    __tablename__ = "PdsDistrictMaster"

    DistrictID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    StateID: Mapped[int] = mapped_column(Integer, ForeignKey("PdsStateMaster.StateID"), nullable=False)
    DistrictCode: Mapped[str] = mapped_column(Unicode(20), nullable=False)
    DistrictName: Mapped[str] = mapped_column(Unicode(120), nullable=False)
    Headquarters: Mapped[str | None] = mapped_column(Unicode(120), nullable=True)
    DivisionName: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    Source: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    ActiveStatus: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    CreatedBy: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ModifiedBy: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    ModifiedDate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PdsDsoMaster(db.Model):
    __tablename__ = "PdsDsoMaster"

    DsoID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    DistrictID: Mapped[int] = mapped_column(Integer, ForeignKey("PdsDistrictMaster.DistrictID"), nullable=False)
    DsoCode: Mapped[str] = mapped_column(Unicode(40), nullable=False)
    DsoName: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    OfficerName: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    MobileNumber: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    Address: Mapped[str | None] = mapped_column(Unicode(400), nullable=True)
    Source: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    ActiveStatus: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    CreatedBy: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ModifiedBy: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    ModifiedDate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PdsAroMaster(db.Model):
    __tablename__ = "PdsAroMaster"

    AroID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    DsoID: Mapped[int] = mapped_column(Integer, ForeignKey("PdsDsoMaster.DsoID"), nullable=False)
    AroCode: Mapped[str] = mapped_column(Unicode(40), nullable=False)
    AroName: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    OfficerName: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    MobileNumber: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    Address: Mapped[str | None] = mapped_column(Unicode(400), nullable=True)
    Source: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    ActiveStatus: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    CreatedBy: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ModifiedBy: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    ModifiedDate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PdsFpsMaster(db.Model):
    __tablename__ = "PdsFpsMaster"

    FpsRowID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    DistrictID: Mapped[int] = mapped_column(Integer, ForeignKey("PdsDistrictMaster.DistrictID"), nullable=False)
    DsoID: Mapped[int | None] = mapped_column(Integer, ForeignKey("PdsDsoMaster.DsoID"), nullable=True)
    AroID: Mapped[int | None] = mapped_column(Integer, ForeignKey("PdsAroMaster.AroID"), nullable=True)
    FpsCode: Mapped[str] = mapped_column(Unicode(80), nullable=False)
    ExistingFpsId: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    FpsName: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    DealerName: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    TehsilName: Mapped[str | None] = mapped_column(Unicode(120), nullable=True)
    VillageName: Mapped[str | None] = mapped_column(Unicode(120), nullable=True)
    PinCode: Mapped[str | None] = mapped_column(Unicode(12), nullable=True)
    MobileNumber: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    Address: Mapped[str | None] = mapped_column(Unicode(400), nullable=True)
    Source: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    ActiveStatus: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    CreatedBy: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ModifiedBy: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    ModifiedDate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PdsRationCardMaster(db.Model):
    __tablename__ = "PdsRationCardMaster"

    CardID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    FpsRowID: Mapped[int] = mapped_column(Integer, ForeignKey("PdsFpsMaster.FpsRowID"), nullable=False)
    RcNumber: Mapped[str] = mapped_column(Unicode(80), nullable=False)
    ExistingRcNumber: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    SchemeName: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    HofName: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    MemberCount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    MobileNumber: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    Source: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    ActiveStatus: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    CreatedBy: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ModifiedBy: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    ModifiedDate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PdsGeoImport(db.Model):
    __tablename__ = "PdsGeoImport"

    ImportKey: Mapped[str] = mapped_column(Unicode(80), primary_key=True)
    Source: Mapped[str | None] = mapped_column(Unicode(260), nullable=True)
    ImportRowCount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    Detail: Mapped[str | None] = mapped_column(Unicode(500), nullable=True)
    ImportedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False)

