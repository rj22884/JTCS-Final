"""Resolve SHCIL Stamp / e-Court purchase wallets after Bank Master edits.

Stamp duty posts to account 0213UK1423304 (SHCILStamp).
e-Court purchase posts to account HUKECFUK1423304 (SHCIL-e-Court).

Older rows stored the alias (SHCILStamp / SHCILECourt) in AccountNumber.
Lookup matches these live account numbers first, then alias fields.
"""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.transactions import JtcsBankAccountMaster, JtcsBankTransaction

STAMP_PURCHASE_ALIASES = ("SHCILSTAMP",)
STAMP_PURCHASE_DESCRIPTION = "STAMP PURCHASE"
STAMP_PURCHASE_ACCOUNT_NUMBERS = ("0213UK1423304",)
ECOURT_PURCHASE_ALIASES = ("SHCILECOURT",)
ECOURT_PURCHASE_DESCRIPTION = "E-COURT PURCHASE"
ECOURT_PURCHASE_ACCOUNT_NUMBERS = ("HUKECFUK1423304",)

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


def account_matches_numbers(account: JtcsBankAccountMaster, numbers: tuple[str, ...]) -> bool:
    """Exact Account Number / Masked Account Number match (0213UK1423304, HUKECFUK1423304)."""
    tokens = {normalize_bank_alias(number) for number in numbers if normalize_bank_alias(number)}
    if not tokens:
        return False
    candidates = {
        normalize_bank_alias(account.AccountNumber),
        normalize_bank_alias(account.MaskedAccountNumber),
    }
    return any(candidate in tokens for candidate in candidates if candidate)


def _normalized_col(column):
    return func.upper(
        func.replace(
            func.replace(func.ltrim(func.rtrim(func.coalesce(column, ""))), " ", ""),
            "-",
            "",
        )
    )


def _rank_alias_match(
    account: JtcsBankAccountMaster,
    aliases: tuple[str, ...],
    account_numbers: tuple[str, ...] = (),
) -> int:
    if account_matches_numbers(account, account_numbers):
        return -1
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


def _find_from_master(
    session: Session,
    aliases: tuple[str, ...],
    account_numbers: tuple[str, ...] = (),
) -> JtcsBankAccountMaster | None:
    accounts = list(
        session.scalars(
            select(JtcsBankAccountMaster).where(
                JtcsBankAccountMaster.ActiveStatus == True  # noqa: E712
            )
        ).all()
    )
    matches = [
        account
        for account in accounts
        if account_matches_numbers(account, account_numbers)
        or account_matches_aliases(account, aliases)
    ]
    if not matches:
        return None
    matches.sort(
        key=lambda account: (
            _rank_alias_match(account, aliases, account_numbers),
            account.JtcsBankAccountID,
        )
    )
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
    session: Session,
    aliases: tuple[str, ...],
    account_numbers: tuple[str, ...] = (),
) -> JtcsBankAccountMaster | None:
    tokens = [
        normalize_bank_alias(token)
        for token in (*aliases, *account_numbers)
        if normalize_bank_alias(token)
    ]
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


def _account_is_purpose(
    account: JtcsBankAccountMaster | None,
    aliases: tuple[str, ...],
    account_numbers: tuple[str, ...],
) -> bool:
    if account is None:
        return False
    return account_matches_numbers(account, account_numbers) or account_matches_aliases(
        account, aliases
    )


def find_purpose_bank_account(
    session: Session,
    aliases: tuple[str, ...],
    *,
    purchase_description: str | None = None,
    account_numbers: tuple[str, ...] = (),
) -> JtcsBankAccountMaster | None:
    account = _find_from_master(session, aliases, account_numbers)
    if account is not None:
        return account
    if purchase_description:
        account = _find_from_purchase_description(session, purchase_description)
        if _account_is_purpose(account, aliases, account_numbers):
            return account
    account = _find_from_ledger_snapshot(session, aliases, account_numbers)
    if _account_is_purpose(account, aliases, account_numbers):
        return account
    return None


def find_stamp_purchase_bank(session: Session) -> JtcsBankAccountMaster | None:
    return find_purpose_bank_account(
        session,
        STAMP_PURCHASE_ALIASES,
        purchase_description=STAMP_PURCHASE_DESCRIPTION,
        account_numbers=STAMP_PURCHASE_ACCOUNT_NUMBERS,
    )


def find_ecourt_purchase_bank(session: Session) -> JtcsBankAccountMaster | None:
    return find_purpose_bank_account(
        session,
        ECOURT_PURCHASE_ALIASES,
        purchase_description=ECOURT_PURCHASE_DESCRIPTION,
        account_numbers=ECOURT_PURCHASE_ACCOUNT_NUMBERS,
    )


def stamp_purchase_account_id(session: Session) -> int | None:
    account = find_stamp_purchase_bank(session)
    return int(account.JtcsBankAccountID) if account is not None else None


def ecourt_purchase_account_id(session: Session) -> int | None:
    account = find_ecourt_purchase_bank(session)
    return int(account.JtcsBankAccountID) if account is not None else None


def account_is_purpose_wallet(
    session: Session,
    account_id: int,
    aliases: tuple[str, ...],
    *,
    purchase_description: str | None = None,
    account_numbers: tuple[str, ...] = (),
) -> bool:
    """True if this Bank Master row is the named purpose wallet (alias or live lookup)."""
    if not account_id:
        return False
    account = session.get(JtcsBankAccountMaster, int(account_id))
    if _account_is_purpose(account, aliases, account_numbers):
        return True
    current = find_purpose_bank_account(
        session,
        aliases,
        purchase_description=purchase_description,
        account_numbers=account_numbers,
    )
    return current is not None and int(current.JtcsBankAccountID) == int(account_id)


def account_is_stamp_purchase_wallet(session: Session, account_id: int) -> bool:
    return account_is_purpose_wallet(
        session,
        account_id,
        STAMP_PURCHASE_ALIASES,
        purchase_description=STAMP_PURCHASE_DESCRIPTION,
        account_numbers=STAMP_PURCHASE_ACCOUNT_NUMBERS,
    )


def account_is_ecourt_purchase_wallet(session: Session, account_id: int) -> bool:
    return account_is_purpose_wallet(
        session,
        account_id,
        ECOURT_PURCHASE_ALIASES,
        purchase_description=ECOURT_PURCHASE_DESCRIPTION,
        account_numbers=ECOURT_PURCHASE_ACCOUNT_NUMBERS,
    )
