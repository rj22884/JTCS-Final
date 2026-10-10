from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class MenuUserAllow(db.Model):
    __tablename__ = "MenuUserAllow"

    MenuID: Mapped[int] = mapped_column(Integer, primary_key=True)
    UserID: Mapped[int] = mapped_column(Integer, primary_key=True)

    def __repr__(self) -> str:
        return f"<MenuUserAllow menu={self.MenuID} user={self.UserID}>"
