from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.transactions import (
    JTCSDailyTransactionPayment,
    JtcsBankAccountMaster,
    JtcsBankTransaction,
    PaymentModeMaster,
)


class BankMasterRepository:
    def __init__(self, session: Session | None = None):
        self.session = session or db.session
        self._schema_ready = False

    def _column_exists(self, column_name: str) -> bool:
        return (
            self.session.execute(
                text(
                    """
                    SELECT CASE
                        WHEN COL_LENGTH(N'dbo.JtcsBankAccountMaster', :col) IS NULL THEN 0
                        ELSE 1
                    END
                    """
                ),
                {"col": column_name},
            ).scalar()
            == 1
        )

    def ensure_schema(self) -> None:
        if (
            self._schema_ready
            and self._column_exists("QrBillReceived")
            and self._column_exists("AccountPaymentReceived")
            and self._column_exists("ChartGroupID")
            and self._column_exists("OpeningBalanceDrCr")
        ):
            return
        try:
            if not self._column_exists("DisplayOrder"):
                self.session.execute(
                    text(
                        """
                        ALTER TABLE dbo.JtcsBankAccountMaster
                        ADD DisplayOrder INT NOT NULL
                            CONSTRAINT DF_JtcsBankAccountMaster_DisplayOrder DEFAULT (100)
                        """
                    )
                )
                self.session.commit()

            self.session.execute(
                text(
                    """
                    UPDATE dbo.JtcsBankAccountMaster
                    SET DisplayOrder = 1
                    WHERE LOWER(LTRIM(RTRIM(ISNULL(BankName, N'')))) = N'cash'
                       OR LOWER(LTRIM(RTRIM(ISNULL(AccountNumber, N'')))) = N'cash'
                    """
                )
            )
            self.session.commit()

            if not self._column_exists("UpiId"):
                self.session.execute(
                    text(
                        """
                        ALTER TABLE dbo.JtcsBankAccountMaster
                        ADD UpiId NVARCHAR(100) NULL
                        """
                    )
                )
                self.session.commit()

            # SQL Server compiles whole batches — ALTER + UPDATE of new column
            # must be separate statements/commits or it raises invalid column name.
            if not self._column_exists("QrBillReceived"):
                self.session.execute(
                    text(
                        """
                        ALTER TABLE dbo.JtcsBankAccountMaster
                        ADD QrBillReceived BIT NOT NULL
                            CONSTRAINT DF_JtcsBankAccountMaster_QrBillReceived DEFAULT (0)
                        """
                    )
                )
                self.session.commit()
                # First-time only: keep existing payment dropdowns working.
                self.session.execute(
                    text(
                        """
                        UPDATE dbo.JtcsBankAccountMaster
                        SET QrBillReceived = 1
                        WHERE ActiveStatus = 1
                        """
                    )
                )
                self.session.commit()

            if not self._column_exists("AccountPaymentReceived"):
                self.session.execute(
                    text(
                        """
                        ALTER TABLE dbo.JtcsBankAccountMaster
                        ADD AccountPaymentReceived BIT NOT NULL
                            CONSTRAINT DF_JtcsBankAccountMaster_AccountPaymentReceived DEFAULT (0)
                        """
                    )
                )
                self.session.commit()
                # First-time only: keep existing Payment Received dropdowns working.
                if self._column_exists("QrBillReceived"):
                    self.session.execute(
                        text(
                            """
                            UPDATE dbo.JtcsBankAccountMaster
                            SET AccountPaymentReceived = 1
                            WHERE AccountPaymentReceived = 0
                              AND QrBillReceived = 1
                            """
                        )
                    )
                    self.session.commit()

            if not self._column_exists("ChartGroupID"):
                self.session.execute(
                    text(
                        """
                        ALTER TABLE dbo.JtcsBankAccountMaster
                        ADD ChartGroupID INT NULL
                        """
                    )
                )
                self.session.commit()

            if not self._column_exists("OpeningBalanceDrCr"):
                self.session.execute(
                    text(
                        """
                        ALTER TABLE dbo.JtcsBankAccountMaster
                        ADD OpeningBalanceDrCr NVARCHAR(2) NULL
                        """
                    )
                )
                self.session.commit()

            if self._column_exists("ChartGroupID"):
                self.session.execute(
                    text(
                        """
                        IF OBJECT_ID(N'dbo.ChartOfGroupMaster', N'U') IS NOT NULL
                           AND NOT EXISTS (
                               SELECT 1 FROM sys.foreign_keys
                               WHERE name = N'FK_JtcsBankAccountMaster_ChartGroup'
                                 AND parent_object_id = OBJECT_ID(N'dbo.JtcsBankAccountMaster')
                           )
                            ALTER TABLE dbo.JtcsBankAccountMaster
                                ADD CONSTRAINT FK_JtcsBankAccountMaster_ChartGroup
                                FOREIGN KEY (ChartGroupID)
                                REFERENCES dbo.ChartOfGroupMaster (GroupID);
                        """
                    )
                )
                self.session.commit()
                # Defaults: Cash → Cash-in-Hand; others → Bank Accounts
                self.session.execute(
                    text(
                        """
                        IF OBJECT_ID(N'dbo.ChartOfGroupMaster', N'U') IS NOT NULL
                        BEGIN
                            DECLARE @BankGroupID INT = (
                                SELECT TOP 1 GroupID FROM dbo.ChartOfGroupMaster
                                WHERE GroupName = N'Bank Accounts' AND IsActive = 1
                                ORDER BY GroupID
                            );
                            DECLARE @CashGroupID INT = (
                                SELECT TOP 1 GroupID FROM dbo.ChartOfGroupMaster
                                WHERE GroupName = N'Cash-in-Hand' AND IsActive = 1
                                ORDER BY GroupID
                            );

                            IF @CashGroupID IS NOT NULL
                                UPDATE dbo.JtcsBankAccountMaster
                                SET ChartGroupID = @CashGroupID
                                WHERE ChartGroupID IS NULL
                                  AND (
                                      LOWER(LTRIM(RTRIM(ISNULL(BankName, N'')))) = N'cash'
                                      OR LOWER(LTRIM(RTRIM(ISNULL(AccountNumber, N'')))) = N'cash'
                                  );

                            IF @BankGroupID IS NOT NULL
                                UPDATE dbo.JtcsBankAccountMaster
                                SET ChartGroupID = @BankGroupID
                                WHERE ChartGroupID IS NULL
                                  AND NOT (
                                      LOWER(LTRIM(RTRIM(ISNULL(BankName, N'')))) = N'cash'
                                      OR LOWER(LTRIM(RTRIM(ISNULL(AccountNumber, N'')))) = N'cash'
                                  );
                        END
                        """
                    )
                )
                self.session.commit()

            self._schema_ready = (
                self._column_exists("QrBillReceived")
                and self._column_exists("AccountPaymentReceived")
                and self._column_exists("ChartGroupID")
            )
            if not self._schema_ready:
                raise RuntimeError(
                    "Bank Master schema update failed: required columns are missing."
                )
        except Exception:
            self.session.rollback()
            self._schema_ready = False
            raise

    def list_all(self, *, search: str | None = None) -> list[JtcsBankAccountMaster]:
        self.ensure_schema()
        stmt = select(JtcsBankAccountMaster).order_by(
            JtcsBankAccountMaster.DisplayOrder,
            JtcsBankAccountMaster.BankName,
            JtcsBankAccountMaster.JtcsBankAccountID,
        )
        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    JtcsBankAccountMaster.BankName.like(term),
                    JtcsBankAccountMaster.AccountNumber.like(term),
                    JtcsBankAccountMaster.MaskedAccountNumber.like(term),
                    JtcsBankAccountMaster.IFSCCode.like(term),
                    JtcsBankAccountMaster.AccountHolderName.like(term),
                    JtcsBankAccountMaster.AccountType.like(term),
                )
            )
        return list(self.session.scalars(stmt).all())

    def get_by_id(self, account_id: int) -> JtcsBankAccountMaster | None:
        return self.session.get(JtcsBankAccountMaster, account_id)

    def create(self, data: dict) -> JtcsBankAccountMaster:
        now = datetime.utcnow()
        data.setdefault("CreatedDate", now)
        data.setdefault("ModifiedDate", now)
        data.setdefault("ActiveStatus", True)
        row = JtcsBankAccountMaster(**data)
        self.session.add(row)
        self.session.flush()
        return row

    def update(self, row: JtcsBankAccountMaster, data: dict) -> JtcsBankAccountMaster:
        preserve = {"JtcsBankAccountID", "CreatedDate"}
        for key, value in data.items():
            if key not in preserve:
                setattr(row, key, value)
        row.ModifiedDate = datetime.utcnow()
        self.session.flush()
        return row

    def delete(self, row: JtcsBankAccountMaster) -> None:
        self.session.delete(row)
        self.session.flush()

    def usage_count(self, account_id: int) -> int:
        bank_txn = self.session.scalar(
            select(func.count())
            .select_from(JtcsBankTransaction)
            .where(JtcsBankTransaction.JtcsBankAccountID == account_id)
        )
        payment_mode = self.session.scalar(
            select(func.count())
            .select_from(PaymentModeMaster)
            .where(PaymentModeMaster.BankAccountID == account_id)
        )
        payment_line = self.session.scalar(
            select(func.count())
            .select_from(JTCSDailyTransactionPayment)
            .where(JTCSDailyTransactionPayment.BankAccountID == account_id)
        )
        return int(bank_txn or 0) + int(payment_mode or 0) + int(payment_line or 0)
