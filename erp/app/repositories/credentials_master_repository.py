from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.credentials_master import CredentialsMaster


class CredentialsMasterRepository:
    def __init__(self, session: Session | None = None):
        self.session = session or db.session

    def list_all(self, *, search: str | None = None, active_only: bool = False) -> list[CredentialsMaster]:
        stmt = select(CredentialsMaster).order_by(
            CredentialsMaster.Activity,
            CredentialsMaster.CredentialID,
        )
        if active_only:
            stmt = stmt.where(CredentialsMaster.ActiveStatus == True)  # noqa: E712
        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    CredentialsMaster.Activity.like(term),
                    CredentialsMaster.URL.like(term),
                    CredentialsMaster.UserID.like(term),
                    CredentialsMaster.EmailID.like(term),
                    CredentialsMaster.MobileNumber.like(term),
                )
            )
        return list(self.session.scalars(stmt).all())

    def get_by_id(self, credential_id: int) -> CredentialsMaster | None:
        return self.session.get(CredentialsMaster, credential_id)

    def create(self, data: dict) -> CredentialsMaster:
        now = datetime.utcnow()
        data.setdefault("CreatedDate", now)
        data.setdefault("ModifiedDate", now)
        data.setdefault("ActiveStatus", True)
        row = CredentialsMaster(**data)
        self.session.add(row)
        self.session.flush()
        return row

    def update(self, row: CredentialsMaster, data: dict) -> CredentialsMaster:
        preserve = {"CredentialID", "CreatedDate", "CreatedBy"}
        for key, value in data.items():
            if key not in preserve:
                setattr(row, key, value)
        row.ModifiedDate = datetime.utcnow()
        self.session.flush()
        return row

    def delete(self, row: CredentialsMaster) -> None:
        self.session.delete(row)
        self.session.flush()
