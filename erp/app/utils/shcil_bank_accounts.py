"""Resolve SHCIL Stamp / e-Court purchase wallets after Bank Master edits.

These wallets used to store the alias (SHCILStamp / SHCILECourt) in AccountNumber.
Users may change Account Number and Bank Name to real bank details; the same
JtcsBankAccountID remains. Lookup therefore matches alias on several master
fields and falls back to existing purchase ledger rows.
"""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.transactions import JtcsBankAccountMaster, JtcsBankTransaction

STAMP_PURCHASE_ALIASES = ("SHCILSTAMP",)
STAMP_PURCHASE_DESCRIPTION = "STAMP PURCHASE"
ECOURT_PURCHASE_ALIASES = ("SHCILECOURT",)
ECOURT_PURCHASE_DESCRIPTION = "E-COURT PURCHASE"

_MASTER_ALIAS_FIELDS = (
    "AccountNumber",
    "MaskedAccountNumber",
    "BankName",
    "Description",
    "AccountHolderName",
)


def normalize_bank_alias(value: str | None) -> str:
    if not value:
        return ""
    return "".join(ch for ch in str(value).upper() if ch.isalnum())


def _field_matches_aliases(value: str | None, aliases: tuple[str, ...]) -> bool:
    norm = normalize_bank_alias(value)
    if not norm:
        return False
    for alias in aliases:
        token = normalize_bank_alias(alias)
        if token and (norm == token or token in norm):
            return True
    return False


def account_matches_aliases(account: JtcsBankAccountMaster, aliases: tuple[str, ...]) -> bool:
    return any(
        _field_matches_aliases(getattr(account, field, None), aliases)
        for field in _MASTER_ALIAS_FIELDS
    )


def _normalized_col(column):
    return func.upper(
        func.replace(
            func.replace(func.ltrim(func.rtrim(func.coalesce(column, ""))), " ", ""),
            "-",
            "",
        )
    )


def _rank_alias_match(account: JtcsBankAccountMaster, aliases: tuple[str, ...]) -> int:
    tokens = {normalize_bank_alias(alias) for alias in aliases}
    account_number = normalize_bank_alias(account.AccountNumber)
    masked = normalize_bank_alias(account.MaskedAccountNumber)
    if account_number in tokens:
        return 0
    if masked in tokens:
        return 1
    if any(token and token in masked for token in tokens):
        return 2
    return 3


def _active_account(session: Session, account_id: int | None) -> JtcsBankAccountMaster | None:
    if not account_id:
        return None
    account = session.get(JtcsBankAccountMaster, int(account_id))
    if account is None or not account.ActiveStatus:
        return None
    return account


def _find_from_master(session: Session, aliases: tuple[str, ...]) -> JtcsBankAccountMaster | None:
    accounts = list(
        session.scalars(
            select(JtcsBankAccountMaster).where(
                JtcsBankAccountMaster.ActiveStatus == True  # noqa: E712
            )
        ).all()
    )
    matches = [account for account in accounts if account_matches_aliases(account, aliases)]
    if not matches:
        return None
    matches.sort(key=lambda account: (_rank_alias_match(account, aliases), account.JtcsBankAccountID))
    return matches[0]


def _find_from_purchase_description(
    session: Session, purchase_description: str
) -> JtcsBankAccountMaster | None:
    description = purchase_description.strip().upper()
    txn = session.scalars(
        select(JtcsBankTransaction)
        .where(
            func.upper(func.ltrim(func.rtrim(func.coalesce(JtcsBankTransaction.Description, ""))))
            == description
        )
        .where(func.upper(func.coalesce(JtcsBankTransaction.LedgerKind, "")) == "PAYMENT")
        .where(JtcsBankTransaction.JtcsBankAccountID.isnot(None))
        .order_by(JtcsBankTransaction.JtcsBankTransactionID.desc())
        .limit(1)
    ).first()
    if txn is None:
        return None
    return _active_account(session, txn.JtcsBankAccountID)


def _find_from_ledger_snapshot(
    session: Session, aliases: tuple[str, ...]
) -> JtcsBankAccountMaster | None:
    tokens = [normalize_bank_alias(alias) for alias in aliases if normalize_bank_alias(alias)]
    if not tokens:
        return None
    snapshot_match = or_(
        *[
            or_(
                _normalized_col(JtcsBankTransaction.MaskedAccountNumber) == token,
                _normalized_col(JtcsBankTransaction.BankName) == token,
            )
            for token in tokens
        ]
    )
    txn = session.scalars(
        select(JtcsBankTransaction)
        .where(snapshot_match)
        .where(JtcsBankTransaction.JtcsBankAccountID.isnot(None))
        .order_by(JtcsBankTransaction.JtcsBankTransactionID.desc())
        .limit(1)
    ).first()
    if txn is None:
        return None
    return _active_account(session, txn.JtcsBankAccountID)


def find_purpose_bank_account(
    session: Session,
    aliases: tuple[str, ...],
    *,
    purchase_description: str | None = None,
) -> JtcsBankAccountMaster | None:
    account = _find_from_master(session, aliases)
    if account is not None:
        return account
    if purchase_description:
        account = _find_from_purchase_description(session, purchase_description)
        if account is not None:
            return account
    return _find_from_ledger_snapshot(session, aliases)


def find_stamp_purchase_bank(session: Session) -> JtcsBankAccountMaster | None:
    return find_purpose_bank_account(
        session,
        STAMP_PURCHASE_ALIASES,
        purchase_description=STAMP_PURCHASE_DESCRIPTION,
    )


def find_ecourt_purchase_bank(session: Session) -> JtcsBankAccountMaster | None:
    return find_purpose_bank_account(
        session,
        ECOURT_PURCHASE_ALIASES,
        purchase_description=ECOURT_PURCHASE_DESCRIPTION,
    )


def stamp_purchase_account_id(session: Session) -> int | None:
    account = find_stamp_purchase_bank(session)
    return int(account.JtcsBankAccountID) if account is not None else None


def ecourt_purchase_account_id(session: Session) -> int | None:
    account = find_ecourt_purchase_bank(session)
    return int(account.JtcsBankAccountID) if account is not None else None
