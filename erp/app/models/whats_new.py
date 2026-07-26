"""Dashboard What's New entries (auto + published)."""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Integer, Unicode
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class WhatsNewEntry(db.Model):
    __tablename__ = "WhatsNew"

    EntryID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    FeatureKey: Mapped[str] = mapped_column(Unicode(120), nullable=False, unique=True)
    Title: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    Detail: Mapped[str | None] = mapped_column(Unicode(500), nullable=True)
    UrlPath: Mapped[str | None] = mapped_column(Unicode(250), nullable=True)
    Badge: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    EntryDate: Mapped[date] = mapped_column(Date, nullable=False)
    Source: Mapped[str] = mapped_column(Unicode(40), nullable=False, default="manual")
    IsActive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    ModifiedDate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<WhatsNewEntry {self.EntryID}: {self.FeatureKey}>"
