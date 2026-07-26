from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Unicode
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class AccountTypeMaster(db.Model):
    __tablename__ = "AccountTypeMaster"

    AccountTypeID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    AccountTypeCode: Mapped[str] = mapped_column(Unicode(20), nullable=False)
    AccountTypeName: Mapped[str] = mapped_column(Unicode(100), nullable=False)
    Description: Mapped[str | None] = mapped_column(Unicode(255), nullable=True)
    OrderNo: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    IsActive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    CreatedAt: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    UpdatedAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
