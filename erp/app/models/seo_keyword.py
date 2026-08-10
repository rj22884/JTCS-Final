"""SEO keywords managed by administrators for meta, footer, and schema markup."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Unicode
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class SeoKeyword(db.Model):
    __tablename__ = "seo_keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keyword: Mapped[str] = mapped_column(Unicode(255), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<SeoKeyword {self.id}: {self.keyword}>"
