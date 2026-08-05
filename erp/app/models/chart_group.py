from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Unicode
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class ChartOfGroupMaster(db.Model):
    __tablename__ = "ChartOfGroupMaster"

    GroupID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    GroupName: Mapped[str] = mapped_column(Unicode(150), nullable=False)
    UnderType: Mapped[str] = mapped_column(Unicode(20), nullable=False)
    ParentGroupID: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ChartOfGroupMaster.GroupID"), nullable=True
    )
    GroupNature: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    IsActive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    UpdatedDate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
