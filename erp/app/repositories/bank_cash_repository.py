from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.bank_cash import OthersBankCashTransaction, RdAccountMaster
from app.models.transactions import JtcsBankAccountMaster, JtcsBankTransaction


class RdAccountRepository:
    def __init__(self, session: Session | None = None):
        self.session = session or db.session

    def list_all(self, *, search: str | None = None, active_only: bool = False) -> list[RdAccountMaster]:
        stmt = select(RdAccountMaster).order_by(RdAccountMaster.RdName, RdAccountMaster.RdAccountID)
        if active_only:
            stmt = stmt.where(RdAccountMaster.ActiveStatus == True)  # noqa: E712
        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    RdAccountMaster.RdName.like(term),
                    RdAccountMaster.RdNumber.like(term),
                    RdAccountMaster.BankName.like(term),
                )
            )
        return list(self.session.scalars(stmt).all())

    def get_by_id(self, rd_account_id: int) -> RdAccountMaster | None:
        return self.session.get(RdAccountMaster, rd_account_id)

    def create(self, data: dict) -> RdAccountMaster:
        now = datetime.utcnow()
        data.setdefault("CreatedDate", now)
        data.setdefault("ModifiedDate", now)
        data.setdefault("ActiveStatus", True)
        row = RdAccountMaster(**data)
        self.session.add(row)
        self.session.flush()
        return row

    def update(self, row: RdAccountMaster, data: dict) -> RdAccountMaster:
        preserve = {"RdAccountID", "CreatedDate", "CreatedBy"}
        for key, value in data.items():
            if key not in preserve:
                setattr(row, key, value)
        row.ModifiedDate = datetime.utcnow()
        self.session.flush()
        return row

    def delete(self, row: RdAccountMaster) -> None:
        self.session.delete(row)
        self.session.flush()

    def usage_count(self, bank_account_id: int | None) -> int:
        if not bank_account_id:
            return 0
        return int(
            self.session.scalar(
                select(func.count())
                .select_from(JtcsBankTransaction)
                .where(JtcsBankTransaction.JtcsBankAccountID == bank_account_id)
            )
            or 0
        )


class OthersBankCashRepository:
    def __init__(self, session: Session | None = None):
        self.session = session or db.session

    def list_active(self, *, limit: int = 200) -> list[OthersBankCashTransaction]:
        stmt = (
            select(OthersBankCashTransaction)
            .where(OthersBankCashTransaction.IsActive == True)  # noqa: E712
            .order_by(
                OthersBankCashTransaction.WorkDate.desc(),
                OthersBankCashTransaction.EntryID.desc(),
            )
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())

    def get_by_id(self, entry_id: int) -> OthersBankCashTransaction | None:
        return self.session.get(OthersBankCashTransaction, entry_id)

    def create(self, data: dict) -> OthersBankCashTransaction:
        data.setdefault("CreatedDate", datetime.utcnow())
        data.setdefault("IsActive", True)
        row = OthersBankCashTransaction(**data)
        self.session.add(row)
        self.session.flush()
        return row

    def update(self, row: OthersBankCashTransaction, data: dict) -> OthersBankCashTransaction:
        preserve = {"EntryID", "CreatedDate", "CreatedBy", "VoucherNo"}
        for key, value in data.items():
            if key not in preserve:
                setattr(row, key, value)
        self.session.flush()
        return row

    def soft_delete(self, row: OthersBankCashTransaction) -> None:
        row.IsActive = False
        self.session.flush()

    def next_voucher_no(self, work_date) -> str:
        prefix = f"OBC-{work_date.strftime('%Y%m%d')}-"
        stmt = (
            select(OthersBankCashTransaction.VoucherNo)
            .where(OthersBankCashTransaction.VoucherNo.like(f"{prefix}%"))
            .order_by(OthersBankCashTransaction.VoucherNo.desc())
        )
        last = self.session.scalars(stmt).first()
        seq = 1
        if last:
            try:
                seq = int(str(last).rsplit("-", 1)[-1]) + 1
            except ValueError:
                seq = 1
        return f"{prefix}{seq:04d}"

    def list_ledger_accounts(self, *, active_only: bool = True) -> list[JtcsBankAccountMaster]:
        stmt = select(JtcsBankAccountMaster).order_by(
            JtcsBankAccountMaster.AccountType,
            JtcsBankAccountMaster.BankName,
            JtcsBankAccountMaster.JtcsBankAccountID,
        )
        if active_only:
            stmt = stmt.where(JtcsBankAccountMaster.ActiveStatus == True)  # noqa: E712
        return list(self.session.scalars(stmt).all())
