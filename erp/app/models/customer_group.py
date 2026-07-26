from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Unicode
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class CustomerGroupMaster(db.Model):
    __tablename__ = "CustomerGroupMaster"

    GroupID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    GroupCode: Mapped[str] = mapped_column(Unicode(20), nullable=False)
    GroupName: Mapped[str] = mapped_column(Unicode(100), nullable=False)
    TabCodes: Mapped[str] = mapped_column(Unicode(500), nullable=False)
    DisplayOrder: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    ActiveStatus: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
