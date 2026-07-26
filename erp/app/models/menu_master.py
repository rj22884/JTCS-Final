from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Unicode, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


class MenuMaster(db.Model):
    __tablename__ = "MenuMaster"

    MenuID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ParentMenuID: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("MenuMaster.MenuID"), nullable=True
    )
    MenuName: Mapped[str] = mapped_column(Unicode(100), nullable=False)
    MenuIcon: Mapped[str | None] = mapped_column(Unicode(100), nullable=True)
    MenuURL: Mapped[str | None] = mapped_column(Unicode(250), nullable=True)
    DisplayOrder: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    IsActive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    CreatedDate: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.getdate()
    )
    Description: Mapped[str | None] = mapped_column(Unicode(300), nullable=True)
    RoleName: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)

    parent: Mapped["MenuMaster | None"] = relationship(
        "MenuMaster",
        remote_side=[MenuID],
        back_populates="children",
        foreign_keys=[ParentMenuID],
    )
    children: Mapped[list["MenuMaster"]] = relationship(
        "MenuMaster",
        back_populates="parent",
        foreign_keys=[ParentMenuID],
        order_by="MenuMaster.DisplayOrder",
    )

    def to_dict(self) -> dict:
        return {
            "MenuID": self.MenuID,
            "ParentMenuID": self.ParentMenuID,
            "MenuName": self.MenuName,
            "MenuIcon": self.MenuIcon,
            "MenuURL": self.MenuURL,
            "DisplayOrder": self.DisplayOrder,
            "IsActive": self.IsActive,
            "CreatedDate": self.CreatedDate.isoformat() if self.CreatedDate else None,
            "Description": self.Description,
            "RoleName": self.RoleName,
        }

    def __repr__(self) -> str:
        return f"<MenuMaster {self.MenuID}: {self.MenuName}>"
