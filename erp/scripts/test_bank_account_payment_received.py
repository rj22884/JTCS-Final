"""Syntax and unit tests for Bank Master Account Payment Received."""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent

CHANGED_PY = [
    ROOT / "app/models/transactions.py",
    ROOT / "app/repositories/bank_master_repository.py",
    ROOT / "app/repositories/transaction_repository.py",
    ROOT / "app/services/bank_master_service.py",
    ROOT / "app/routes/others_income_expense.py",
    ROOT / "app/utils/bank_account_flags.py",
    ROOT / "scripts/apply_bank_account_payment_received.py",
]


def _load_flags():
    path = ROOT / "app/utils/bank_account_flags.py"
    spec = importlib.util.spec_from_file_location("bank_account_flags", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_python_syntax() -> None:
    for path in CHANGED_PY:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_source_contract() -> None:
    model = (ROOT / "app/models/transactions.py").read_text(encoding="utf-8")
    assert "AccountPaymentReceived" in model

    service = (ROOT / "app/services/bank_master_service.py").read_text(encoding="utf-8")
    assert "account_payment_received" in service
    assert "AccountPaymentReceived" in service

    repo = (ROOT / "app/repositories/transaction_repository.py").read_text(encoding="utf-8")
    assert "account_payment_received_only" in repo
    assert "is_account_payment_received" in repo

    oie = (ROOT / "app/routes/others_income_expense.py").read_text(encoding="utf-8")
    assert "qr_bill_received_only=False" not in oie

    schema = (ROOT / "app/repositories/bank_master_repository.py").read_text(encoding="utf-8")
    assert "DF_JtcsBankAccountMaster_AccountPaymentReceived" in schema


def test_flag_helpers() -> None:
    flags = _load_flags()
    assert flags.form_flag({"AccountPaymentReceived": "1"}, "AccountPaymentReceived") is True
    assert flags.form_flag({"AccountPaymentReceived": "yes"}, "AccountPaymentReceived") is True
    assert flags.form_flag({"AccountPaymentReceived": "0"}, "AccountPaymentReceived") is False
    assert flags.form_flag(
        {"account_payment_received": "true"},
        "AccountPaymentReceived",
        "account_payment_received",
    ) is True
    assert flags.form_flag({}, "AccountPaymentReceived", "account_payment_received") is False

    cash = SimpleNamespace(AccountPaymentReceived=True)
    rd = SimpleNamespace(AccountPaymentReceived=False)
    missing = SimpleNamespace()
    assert flags.is_account_payment_received(cash) is True
    assert flags.is_account_payment_received(rd) is False
    assert flags.is_account_payment_received(missing) is False


def main() -> int:
    test_python_syntax()
    print("OK  python syntax")
    test_source_contract()
    print("OK  source contract")
    test_flag_helpers()
    print("OK  flag helpers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
