from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, Unicode
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


class JTCSDailyTransaction(db.Model):
    __tablename__ = "JTCSDailyTransaction"

    TransactionID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    TransactionDate: Mapped[date] = mapped_column(Date, nullable=False)
    WorkType: Mapped[str] = mapped_column(Unicode(50), nullable=False)
    SubWorkType: Mapped[str | None] = mapped_column(Unicode(100), nullable=True)
    CustomerID: Mapped[int | None] = mapped_column(Integer, ForeignKey("CustomerMaster.CustomerID"), nullable=True)
    StampID: Mapped[int | None] = mapped_column(Integer, ForeignKey("StampMaster.StampID"), nullable=True)
    CustomerName: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    ReferenceNo: Mapped[str | None] = mapped_column(Unicode(100), nullable=True)
    Description: Mapped[str | None] = mapped_column(Unicode(1000), nullable=True)
    IncomeAmount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    ExpenseAmount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    SaleAmount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    PurchaseAmount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    GSTAmount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    TDSAmount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    Quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    Rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    TotalAmount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    BankTransactionID: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("JtcsBankTransaction.JtcsBankTransactionID"), nullable=True
    )
    PaymentModeID: Mapped[int | None] = mapped_column(Integer, nullable=True)
    PaymentSplitCount: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    Status: Mapped[str] = mapped_column(Unicode(50), nullable=False, default="Posted")
    CreatedBy: Mapped[str] = mapped_column(Unicode(150), nullable=False)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ModifiedDate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    Remarks: Mapped[str | None] = mapped_column(Unicode(500), nullable=True)

    bank_transaction: Mapped["JtcsBankTransaction | None"] = relationship(
        "JtcsBankTransaction",
        foreign_keys=[BankTransactionID],
        uselist=False,
    )


class JtcsBankTransaction(db.Model):
    __tablename__ = "JtcsBankTransaction"

    JtcsBankTransactionID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    JtcsBankAccountID: Mapped[int] = mapped_column(Integer, nullable=False)
    BankName: Mapped[str] = mapped_column(Unicode(150), nullable=False)
    MaskedAccountNumber: Mapped[str] = mapped_column(Unicode(50), nullable=False)
    TransactionDate: Mapped[date] = mapped_column(Date, nullable=False)
    Description: Mapped[str | None] = mapped_column(Unicode(1000), nullable=True)
    Debit: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    Credit: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    ClosingBalance: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    ImportedBy: Mapped[str] = mapped_column(Unicode(150), nullable=False)
    ImportedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    Remarks: Mapped[str | None] = mapped_column(Unicode(500), nullable=True)
    IsLocked: Mapped[bool] = mapped_column(nullable=False, default=False)
    SourceTable: Mapped[str | None] = mapped_column(Unicode(50), nullable=True)
    SourceRecordID: Mapped[int | None] = mapped_column(Integer, nullable=True)
    SourceType: Mapped[str | None] = mapped_column(Unicode(50), nullable=True)
    SourceID: Mapped[int | None] = mapped_column(Integer, nullable=True)
    LedgerKind: Mapped[str | None] = mapped_column(Unicode(10), nullable=True)
    PaymentModeID: Mapped[int | None] = mapped_column(Integer, nullable=True)
    PaymentSequence: Mapped[int | None] = mapped_column(Integer, nullable=True)


class JTCSDailyTransactionPayment(db.Model):
    __tablename__ = "JTCSDailyTransactionPayment"

    PaymentLineID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    TransactionID: Mapped[int] = mapped_column(
        Integer, ForeignKey("JTCSDailyTransaction.TransactionID"), nullable=False
    )
    PaymentSequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    PaymentModeID: Mapped[int | None] = mapped_column(Integer, nullable=True)
    BankAccountID: Mapped[int] = mapped_column(Integer, nullable=False)
    Amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    BankTransactionID: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("JtcsBankTransaction.JtcsBankTransactionID"), nullable=True
    )
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class CustomerMaster(db.Model):
    __tablename__ = "CustomerMaster"

    CustomerID: Mapped[int] = mapped_column(Integer, primary_key=True)
    CustomerName: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    MobileNumber: Mapped[str | None] = mapped_column(Unicode(15), nullable=True)
    CustomerStatus: Mapped[str] = mapped_column(Unicode(50), nullable=False, default="Active")
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class JtcsBankAccountMaster(db.Model):
    __tablename__ = "JtcsBankAccountMaster"

    JtcsBankAccountID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    BankName: Mapped[str] = mapped_column(Unicode(150), nullable=False)
    AccountNumber: Mapped[str] = mapped_column(Unicode(50), nullable=False, default="")
    MaskedAccountNumber: Mapped[str | None] = mapped_column(Unicode(50), nullable=True)
    IFSCCode: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    BranchName: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    AccountHolderName: Mapped[str | None] = mapped_column(Unicode(150), nullable=True)
    AccountType: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    Description: Mapped[str | None] = mapped_column(Unicode(500), nullable=True)
    ActiveStatus: Mapped[bool] = mapped_column(nullable=False, default=True)
    QrBillReceived: Mapped[bool] = mapped_column(nullable=False, default=False)
    CreatedDate: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    ModifiedDate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    OpeningBalance: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    OpeningBalanceDate: Mapped[date | None] = mapped_column(Date, nullable=True)
    DisplayOrder: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    UpiId: Mapped[str | None] = mapped_column(Unicode(100), nullable=True)


class PaymentModeMaster(db.Model):
    __tablename__ = "PaymentModeMaster"

    PaymentModeID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    PaymentModeName: Mapped[str] = mapped_column(Unicode(100), nullable=False)
    BankAccountID: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("JtcsBankAccountMaster.JtcsBankAccountID"), nullable=True
    )
    IsActive: Mapped[bool] = mapped_column(nullable=False, default=True)


class TransactionTypeMaster(db.Model):
    __tablename__ = "TransactionTypeMaster"

    TransactionTypeID: Mapped[int] = mapped_column(Integer, primary_key=True)
    TransactionTypeName: Mapped[str] = mapped_column(Unicode(100), nullable=False)


class WorkTypeMaster(db.Model):
    __tablename__ = "WorkTypeMaster"

    WorkTypeID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    WorkTypeName: Mapped[str] = mapped_column(Unicode(100), nullable=False)
    SubWorkType: Mapped[str] = mapped_column(Unicode(100), nullable=False)
    ActiveStatus: Mapped[bool] = mapped_column(nullable=False, default=True)
