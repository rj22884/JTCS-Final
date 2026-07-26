from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Unicode
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class CredentialsMaster(db.Model):
    __tablename__ = "CredentialsMaster"

    CredentialID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    Activity: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    URL: Mapped[str | None] = mapped_column(Unicode(500), nullable=True)
    UserID: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    Password: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    EmailID: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    MobileNumber: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    ActiveStatus: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    CreatedBy: Mapped[str | None] = mapped_column(Unicode(100), nullable=True)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    ModifiedDate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
