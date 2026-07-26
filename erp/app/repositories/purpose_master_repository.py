from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.bank_cash import PurposeMaster


class PurposeMasterRepository:
    def __init__(self, session: Session | None = None):
        self.session = session or db.session

    def list_all(self, *, search: str | None = None, active_only: bool = False) -> list[PurposeMaster]:
        stmt = select(PurposeMaster).order_by(PurposeMaster.PurposeName, PurposeMaster.PurposeID)
        if active_only:
            stmt = stmt.where(PurposeMaster.ActiveStatus == True)  # noqa: E712
        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    PurposeMaster.PurposeName.like(term),
                    PurposeMaster.Description.like(term),
                )
            )
        return list(self.session.scalars(stmt).all())

    def get_by_id(self, purpose_id: int) -> PurposeMaster | None:
        return self.session.get(PurposeMaster, purpose_id)

    def create(self, data: dict) -> PurposeMaster:
        now = datetime.utcnow()
        data.setdefault("CreatedDate", now)
        data.setdefault("ModifiedDate", now)
        data.setdefault("ActiveStatus", True)
        row = PurposeMaster(**data)
        self.session.add(row)
        self.session.flush()
        return row

    def update(self, row: PurposeMaster, data: dict) -> PurposeMaster:
        preserve = {"PurposeID", "CreatedDate", "CreatedBy"}
        for key, value in data.items():
            if key not in preserve:
                setattr(row, key, value)
        row.ModifiedDate = datetime.utcnow()
        self.session.flush()
        return row

    def delete(self, row: PurposeMaster) -> None:
        self.session.delete(row)
        self.session.flush()
