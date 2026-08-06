from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.customer_master.constants import DB_TO_FORM, FORM_TO_DB
from app.extensions import db
from app.models.transactions import CustomerMaster


_CUSTOMER_SCHEMA_READY = False


class CustomerRepository:
    def __init__(self, session: Session | None = None):
        self.session = session or db.session

    def ensure_schema(self) -> None:
        """Add Customer Master columns used by forms (idempotent)."""
        global _CUSTOMER_SCHEMA_READY
        if _CUSTOMER_SCHEMA_READY:
            return
        # Separate ALTERs — SQL Server cannot compile multi-column IF batches safely.
        for stmt in (
            """
            IF COL_LENGTH(N'dbo.CustomerMaster', N'OpeningBalance') IS NULL
                ALTER TABLE dbo.CustomerMaster ADD OpeningBalance DECIMAL(18, 2) NULL;
            """,
            """
            IF COL_LENGTH(N'dbo.CustomerMaster', N'OpeningBalanceDate') IS NULL
                ALTER TABLE dbo.CustomerMaster ADD OpeningBalanceDate DATE NULL;
            """,
            """
            IF COL_LENGTH(N'dbo.CustomerMaster', N'OpeningBalanceDrCr') IS NULL
                ALTER TABLE dbo.CustomerMaster ADD OpeningBalanceDrCr NVARCHAR(2) NULL;
            """,
            """
            IF COL_LENGTH(N'dbo.CustomerMaster', N'FilingFrequency') IS NULL
                ALTER TABLE dbo.CustomerMaster ADD FilingFrequency NVARCHAR(20) NULL;
            """,
            """
            IF COL_LENGTH(N'dbo.CustomerMaster', N'ModifiedDate') IS NULL
                ALTER TABLE dbo.CustomerMaster ADD ModifiedDate DATETIME2 NULL;
            """,
            """
            IF COL_LENGTH(N'dbo.CustomerMaster', N'District') IS NULL
                ALTER TABLE dbo.CustomerMaster ADD District NVARCHAR(100) NULL;
            """,
            """
            IF COL_LENGTH(N'dbo.CustomerMaster', N'StateGstCode') IS NULL
                ALTER TABLE dbo.CustomerMaster ADD StateGstCode NVARCHAR(2) NULL;
            """,
            """
            IF COL_LENGTH(N'dbo.CustomerMaster', N'PhotoPath') IS NULL
                ALTER TABLE dbo.CustomerMaster ADD PhotoPath NVARCHAR(500) NULL;
            """,
            """
            IF COL_LENGTH(N'dbo.CustomerMaster', N'AadhaarReferenceId') IS NULL
                ALTER TABLE dbo.CustomerMaster ADD AadhaarReferenceId NVARCHAR(100) NULL;
            """,
            """
            IF COL_LENGTH(N'dbo.CustomerMaster', N'PortalPassword') IS NULL
                ALTER TABLE dbo.CustomerMaster ADD PortalPassword NVARCHAR(255) NULL;
            """,
            """
            IF COL_LENGTH(N'dbo.CustomerMaster', N'PasswordChanged') IS NULL
                ALTER TABLE dbo.CustomerMaster ADD PasswordChanged BIT NOT NULL
                    CONSTRAINT DF_CustomerMaster_PasswordChanged DEFAULT (0);
            """,
            """
            IF COL_LENGTH(N'dbo.CustomerMaster', N'LastLogin') IS NULL
                ALTER TABLE dbo.CustomerMaster ADD LastLogin DATETIME2 NULL;
            """,
            """
            IF COL_LENGTH(N'dbo.CustomerMaster', N'LastPasswordChange') IS NULL
                ALTER TABLE dbo.CustomerMaster ADD LastPasswordChange DATETIME2 NULL;
            """,
            """
            IF COL_LENGTH(N'dbo.CustomerMaster', N'PasswordResetDate') IS NULL
                ALTER TABLE dbo.CustomerMaster ADD PasswordResetDate DATETIME2 NULL;
            """,
            """
            IF COL_LENGTH(N'dbo.CustomerMaster', N'FailedLoginCount') IS NULL
                ALTER TABLE dbo.CustomerMaster ADD FailedLoginCount INT NOT NULL
                    CONSTRAINT DF_CustomerMaster_FailedLoginCount DEFAULT (0);
            """,
            """
            IF COL_LENGTH(N'dbo.CustomerMaster', N'AccountLocked') IS NULL
                ALTER TABLE dbo.CustomerMaster ADD AccountLocked BIT NOT NULL
                    CONSTRAINT DF_CustomerMaster_AccountLocked DEFAULT (0);
            """,
        ):
            self.session.execute(text(stmt))
            self.session.commit()
        # Link table only — does not alter CustomerMaster columns.
        self.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.CustomerIncomeExpenseWorkLink', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.CustomerIncomeExpenseWorkLink (
                        CustomerID INT NOT NULL,
                        WorkID     INT NOT NULL,
                        CONSTRAINT PK_CustomerIncomeExpenseWorkLink PRIMARY KEY (CustomerID, WorkID),
                        CONSTRAINT FK_CustomerIEWorkLink_Customer
                            FOREIGN KEY (CustomerID) REFERENCES dbo.CustomerMaster (CustomerID),
                        CONSTRAINT FK_CustomerIEWorkLink_Work
                            FOREIGN KEY (WorkID) REFERENCES dbo.WorkMaster (WorkID)
                    );
                    CREATE INDEX IX_CustomerIEWorkLink_WorkID
                        ON dbo.CustomerIncomeExpenseWorkLink (WorkID);
                END
                """
            )
        )
        self.session.commit()
        self.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.CustomerPortalLoginLog', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.CustomerPortalLoginLog (
                        LogID           BIGINT IDENTITY(1, 1) NOT NULL,
                        CustomerID      INT NULL,
                        UserIdInput     NVARCHAR(255) NOT NULL,
                        DetectedType    NVARCHAR(20) NULL,
                        AttemptResult   NVARCHAR(40) NOT NULL,
                        IpAddress       NVARCHAR(64) NULL,
                        UserAgent       NVARCHAR(500) NULL,
                        CreatedDate     DATETIME2 NOT NULL
                            CONSTRAINT DF_CustomerPortalLoginLog_CreatedDate DEFAULT (SYSUTCDATETIME()),
                        CONSTRAINT PK_CustomerPortalLoginLog PRIMARY KEY (LogID)
                    );
                    CREATE INDEX IX_CustomerPortalLoginLog_CustomerID
                        ON dbo.CustomerPortalLoginLog (CustomerID);
                    CREATE INDEX IX_CustomerPortalLoginLog_CreatedDate
                        ON dbo.CustomerPortalLoginLog (CreatedDate);
                END
                """
            )
        )
        self.session.commit()
        # Seed default portal password hash for customers that do not have one yet.
        pending = self.session.execute(
            text(
                """
                SELECT COUNT(1)
                FROM dbo.CustomerMaster
                WHERE PortalPassword IS NULL
                   OR LTRIM(RTRIM(PortalPassword)) = N''
                """
            )
        ).scalar()
        if int(pending or 0) > 0:
            from app.utils.security import hash_password

            self.session.execute(
                text(
                    """
                    UPDATE dbo.CustomerMaster
                    SET PortalPassword = :pwd,
                        PasswordChanged = ISNULL(PasswordChanged, 0),
                        FailedLoginCount = ISNULL(FailedLoginCount, 0),
                        AccountLocked = ISNULL(AccountLocked, 0)
                    WHERE PortalPassword IS NULL
                       OR LTRIM(RTRIM(PortalPassword)) = N''
                    """
                ),
                {"pwd": hash_password("Admin@123")},
            )
            self.session.commit()
        _CUSTOMER_SCHEMA_READY = True

    @staticmethod
    def _normalize_mobile(value: str | None) -> str:
        digits = re.sub(r"\D", "", value or "")
        if len(digits) >= 10:
            return digits[-10:]
        return digits

    # Shared placeholder when PAN is not available — may be reused across customers.
    PLACEHOLDER_PAN = "PANNOTAVBL"

    @staticmethod
    def _normalize_pan(value: str | None) -> str | None:
        raw = (value or "").strip().upper()
        return raw or None

    @classmethod
    def is_placeholder_pan(cls, value: str | None) -> bool:
        return (cls._normalize_pan(value) or "") == cls.PLACEHOLDER_PAN

    @staticmethod
    def _serialize_value(value):
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, Decimal):
            return f"{value.quantize(Decimal('0.01')):.2f}"
        return value

    def _map_row_to_form(self, row: dict) -> dict:
        data = {"customer_id": row.get("CustomerID")}
        for db_col, form_key in DB_TO_FORM.items():
            if db_col in row:
                data[form_key] = self._serialize_value(row.get(db_col))
        return data

    def search(self, query: str, *, limit: int = 20) -> list[dict]:
        needle = (query or "").strip()
        if len(needle) < 2:
            return []

        self.ensure_schema()
        mobile = self._normalize_mobile(needle)
        digits = re.sub(r"\D", "", needle)
        like = f"%{needle}%"
        like_upper = f"%{needle.upper()}%"
        rows = self.session.execute(
            text(
                """
                SELECT TOP (:lim) CustomerID, CustomerName, MobileNumber, PANNumber,
                       AadhaarNumber, Pincode, AddressLine1, AddressLine2, State, Country, EmailID,
                       FilingFrequency
                FROM CustomerMaster
                WHERE CustomerStatus = N'Active'
                  AND (
                    UPPER(LTRIM(RTRIM(CustomerName))) LIKE UPPER(:like)
                    OR MobileNumber LIKE :mobile_like
                    OR UPPER(LTRIM(RTRIM(PANNumber))) LIKE :like_upper
                    OR REPLACE(AadhaarNumber, ' ', '') LIKE :digits_like
                  )
                ORDER BY
                  CASE
                    WHEN UPPER(LTRIM(RTRIM(CustomerName))) LIKE UPPER(:like_prefix) THEN 0
                    ELSE 1
                  END,
                  CustomerName
                """
            ),
            {
                "lim": limit,
                "like": like,
                "like_prefix": f"{needle}%",
                "like_upper": like_upper,
                "mobile_like": f"%{mobile}%",
                "digits_like": f"%{digits}%",
            },
        ).mappings().all()
        return [
            {
                "customer_id": row["CustomerID"],
                "customer_name": row["CustomerName"] or "",
                "mobile_number": row["MobileNumber"] or "",
                "pan_number": row["PANNumber"] or "",
                "aadhaar_number": row["AadhaarNumber"] or "",
                "pincode": row["Pincode"] or "",
                "address_line1": row["AddressLine1"] or "",
                "address_line2": row["AddressLine2"] or "",
                "state": row["State"] or "",
                "country": row["Country"] or "",
                "email_id": row.get("EmailID") or "",
                "filing_frequency": row.get("FilingFrequency") or "",
            }
            for row in rows
        ]

    def list_master(
        self,
        *,
        search: str | None = None,
        customer_group: str | None = None,
        status: str | None = None,
        limit: int = 500,
    ) -> list[dict]:
        sql = """
            SELECT TOP (:lim)
                CustomerID, CustomerGroup, CustomerType, CustomerName, MobileNumber,
                PANNumber, EmailID, City, CustomerStatus, CreatedDate
            FROM CustomerMaster
            WHERE 1 = 1
        """
        params: dict = {"lim": limit}
        if search:
            sql += """
              AND (
                CustomerName LIKE :search
                OR MobileNumber LIKE :search
                OR PANNumber LIKE :search_upper
                OR EmailID LIKE :search
              )
            """
            params["search"] = f"%{search.strip()}%"
            params["search_upper"] = f"%{search.strip().upper()}%"
        if customer_group:
            sql += " AND CustomerGroup = :grp"
            params["grp"] = customer_group.strip().upper()
        if status:
            sql += " AND CustomerStatus = :status"
            params["status"] = status.strip()
        sql += " ORDER BY CustomerName, CustomerID DESC"
        rows = self.session.execute(text(sql), params).mappings().all()
        return [
            {
                "customer_id": row["CustomerID"],
                "customer_group": row.get("CustomerGroup") or "",
                "customer_type": row.get("CustomerType") or "",
                "customer_name": row.get("CustomerName") or "",
                "mobile_number": row.get("MobileNumber") or "",
                "pan_number": row.get("PANNumber") or "",
                "email_id": row.get("EmailID") or "",
                "city": row.get("City") or "",
                "customer_status": row.get("CustomerStatus") or "Active",
                "created_date": self._serialize_value(row.get("CreatedDate")),
            }
            for row in rows
        ]

    def get_by_id(self, customer_id: int) -> CustomerMaster | None:
        return self.session.get(CustomerMaster, customer_id)

    def get_detail(self, customer_id: int) -> dict:
        self.ensure_schema()
        result = self.session.execute(
            text("SELECT * FROM CustomerMaster WHERE CustomerID = :id"),
            {"id": customer_id},
        ).mappings().first()
        if not result:
            raise ValueError("Customer not found.")
        return dict(result)

    def get_full(self, customer_id: int) -> dict:
        return self._map_row_to_form(self.get_detail(customer_id))

    def create(self, payload: dict) -> dict:
        """Quick create for followup inline modal (existing validation)."""
        name = (payload.get("customer_name") or payload.get("CustomerName") or "").strip()
        mobile = self._normalize_mobile(payload.get("mobile_number") or payload.get("MobileNumber"))
        pan = self._normalize_pan(payload.get("pan_number") or payload.get("PANNumber"))
        aadhaar = re.sub(r"\D", "", (payload.get("aadhaar_number") or payload.get("AadhaarNumber") or ""))
        pincode = (payload.get("pincode") or payload.get("Pincode") or "").strip()
        address1 = (payload.get("address_line1") or payload.get("AddressLine1") or "").strip()
        address2 = (payload.get("address_line2") or payload.get("AddressLine2") or "").strip()
        state = (payload.get("state") or payload.get("State") or "").strip()
        country = (payload.get("country") or payload.get("Country") or "India").strip()
        district = (payload.get("district") or payload.get("District") or "").strip()
        city = (payload.get("city") or payload.get("City") or "").strip()
        state_gst_code = re.sub(
            r"\D", "", (payload.get("state_gst_code") or payload.get("StateGstCode") or "")
        )[:2]
        email = (payload.get("email_id") or payload.get("EmailID") or "").strip() or None

        if not name:
            raise ValueError("Customer name is required.")
        if not mobile or len(mobile) != 10:
            raise ValueError("Valid 10-digit mobile number is required.")
        if not pan:
            raise ValueError("PAN is required.")
        if not aadhaar or len(aadhaar) != 12:
            raise ValueError("Valid 12-digit Aadhaar is required.")
        if not pincode:
            raise ValueError("Pincode is required.")
        if not address1:
            raise ValueError("Address Line 1 is required.")

        self.ensure_schema()
        now = datetime.utcnow()
        result = self.session.execute(
            text(
                """
                INSERT INTO CustomerMaster (
                    CustomerName, MobileNumber, PANNumber, AadhaarNumber,
                    Pincode, AddressLine1, AddressLine2, State, Country, District, City, StateGstCode, EmailID,
                    CustomerStatus, CreatedDate
                )
                OUTPUT INSERTED.CustomerID
                VALUES (
                    :name, :mobile, :pan, :aadhaar,
                    :pincode, :addr1, :addr2, :state, :country, :district, :city, :state_gst_code, :email,
                    N'Active', :created
                )
                """
            ),
            {
                "name": name[:255],
                "mobile": mobile,
                "pan": pan,
                "aadhaar": aadhaar,
                "pincode": pincode[:10],
                "addr1": address1[:300],
                "addr2": (address2 or None),
                "state": (state or None),
                "country": (country or "India")[:100],
                "district": (district[:100] if district else None),
                "city": (city[:100] if city else None),
                "state_gst_code": (state_gst_code or None),
                "email": (email[:255] if email else None),
                "created": now,
            },
        ).scalar_one()
        self.session.flush()
        self.ensure_portal_password_defaults(int(result))
        return self._map_row_to_form(self.get_detail(int(result)))

    def update_email(self, customer_id: int, email_id: str | None) -> None:
        """Update CustomerMaster.EmailID (used by DSC Followup entry save)."""
        email = (email_id or "").strip() or None
        self.session.execute(
            text(
                """
                UPDATE CustomerMaster
                SET EmailID = :email, ModifiedDate = :now
                WHERE CustomerID = :id
                """
            ),
            {
                "email": (email[:255] if email else None),
                "now": datetime.utcnow(),
                "id": int(customer_id),
            },
        )
        self.session.flush()

    def _prepare_db_values(self, payload: dict) -> dict[str, object]:
        values: dict[str, object] = {}
        for form_key, db_col in FORM_TO_DB.items():
            if form_key not in payload and form_key.replace("_", "") not in payload:
                continue
            raw = payload.get(form_key)
            if raw is None:
                raw = payload.get(form_key.replace("_", ""))
            if raw is None:
                continue
            if form_key in {"date_of_birth", "date_of_incorporation", "opening_balance_date"}:
                text_val = str(raw).strip()
                if not text_val:
                    values[db_col] = None
                else:
                    values[db_col] = date.fromisoformat(text_val[:10])
            elif form_key == "opening_balance":
                text_val = str(raw).strip().replace(",", "")
                if not text_val:
                    values[db_col] = None
                else:
                    try:
                        amount = Decimal(text_val)
                    except (InvalidOperation, ValueError) as exc:
                        raise ValueError("Opening Balance must be a valid number.") from exc
                    if amount < 0:
                        raise ValueError("Opening Balance cannot be negative. Use Dr / Cr.")
                    values[db_col] = amount.quantize(Decimal("0.01"))
            elif form_key == "opening_balance_dr_cr":
                token = str(raw).strip().upper()
                if not token:
                    values[db_col] = None
                elif token in {"DR", "D", "DEBIT"}:
                    values[db_col] = "Dr"
                elif token in {"CR", "C", "CREDIT"}:
                    values[db_col] = "Cr"
                else:
                    raise ValueError("Opening Balance type must be Dr or Cr.")
            elif form_key in {"mobile_number", "alternate_mobile", "whatsapp_number"}:
                values[db_col] = self._normalize_mobile(str(raw)) or None
            elif form_key == "pan_number":
                values[db_col] = self._normalize_pan(str(raw))
            elif form_key == "aadhaar_number":
                digits = re.sub(r"\D", "", str(raw))
                values[db_col] = digits or None
            elif form_key == "customer_group":
                values[db_col] = (str(raw).strip().upper() or None)
            else:
                text_val = str(raw).strip()
                values[db_col] = text_val or None
        if "CustomerStatus" not in values:
            values["CustomerStatus"] = "Active"

        # Keep OB fields consistent: amount with type, or clear all when empty
        ob_amount = values.get("OpeningBalance")
        ob_type = values.get("OpeningBalanceDrCr")
        if ob_amount is not None and ob_amount != Decimal("0.00") and not ob_type:
            # Fallback Dr; UI normally sends group-based Dr/Cr.
            values["OpeningBalanceDrCr"] = "Dr"
        if (
            ob_amount is not None
            and ob_amount != Decimal("0.00")
            and not values.get("OpeningBalanceDate")
        ):
            raise ValueError("Opening Balance Date is required when Opening Balance is entered.")
        if (ob_amount is None or ob_amount == Decimal("0.00")) and not values.get("OpeningBalanceDate"):
            if "OpeningBalance" in values:
                values["OpeningBalance"] = None
            if "OpeningBalanceDrCr" in values and not ob_type:
                values["OpeningBalanceDrCr"] = None
        return values

    def save_full(self, payload: dict, *, customer_id: int | None = None) -> dict:
        self.ensure_schema()
        values = self._prepare_db_values(payload)
        now = datetime.utcnow()
        if customer_id:
            values["ModifiedDate"] = now
            set_clause = ", ".join(f"{col} = :{col}" for col in values)
            params = dict(values)
            params["CustomerID"] = customer_id
            self.session.execute(
                text(f"UPDATE CustomerMaster SET {set_clause} WHERE CustomerID = :CustomerID"),
                params,
            )
            self.session.flush()
            return self.get_full(customer_id)

        values["CreatedDate"] = now
        cols = list(values.keys())
        placeholders = ", ".join(f":{col}" for col in cols)
        col_names = ", ".join(cols)
        new_id = self.session.execute(
            text(
                f"INSERT INTO CustomerMaster ({col_names}) "
                f"OUTPUT INSERTED.CustomerID VALUES ({placeholders})"
            ),
            values,
        ).scalar_one()
        self.session.flush()
        self.ensure_portal_password_defaults(int(new_id))
        return self.get_full(int(new_id))

    def ensure_portal_password_defaults(self, customer_id: int) -> None:
        """Ensure a customer has the default portal password (Admin@123) when unset."""
        self.ensure_schema()
        from app.utils.security import hash_password

        row = self.session.execute(
            text(
                """
                SELECT PortalPassword
                FROM dbo.CustomerMaster
                WHERE CustomerID = :id
                """
            ),
            {"id": int(customer_id)},
        ).first()
        if not row:
            return
        current = (row[0] or "").strip()
        if current:
            return
        self.session.execute(
            text(
                """
                UPDATE dbo.CustomerMaster
                SET PortalPassword = :pwd,
                    PasswordChanged = 0,
                    FailedLoginCount = ISNULL(FailedLoginCount, 0),
                    AccountLocked = ISNULL(AccountLocked, 0)
                WHERE CustomerID = :id
                """
            ),
            {"pwd": hash_password("Admin@123"), "id": int(customer_id)},
        )
        self.session.flush()

    def deactivate(self, customer_id: int) -> None:
        self.session.execute(
            text(
                "UPDATE CustomerMaster SET CustomerStatus = N'Inactive', ModifiedDate = :now "
                "WHERE CustomerID = :id"
            ),
            {"id": customer_id, "now": datetime.utcnow()},
        )
        self.session.flush()

    def _duplicate_customer_dict(self, row) -> dict:
        return {
            "customer_id": row["CustomerID"],
            "customer_name": row.get("CustomerName") or "",
            "mobile_number": row.get("MobileNumber") or "",
            "pan_number": row.get("PANNumber") or "",
            "aadhaar_number": row.get("AadhaarNumber") or "",
            "customer_group": row.get("CustomerGroup") or "",
        }

    def find_by_pan(self, pan: str, *, exclude_customer_id: int | None = None) -> dict | None:
        normalized = self._normalize_pan(pan)
        if not normalized:
            return None
        # Only PANNOTAVBL may be duplicated; all other PANs stay unique.
        if self.is_placeholder_pan(normalized):
            return None
        sql = """
            SELECT TOP 1 CustomerID, CustomerName, MobileNumber, PANNumber, AadhaarNumber, CustomerGroup
            FROM CustomerMaster
            WHERE UPPER(LTRIM(RTRIM(PANNumber))) = :pan
              AND CustomerStatus <> N'Inactive'
        """
        params = {"pan": normalized}
        if exclude_customer_id:
            sql += " AND CustomerID <> :exclude_id"
            params["exclude_id"] = exclude_customer_id
        row = self.session.execute(text(sql), params).mappings().first()
        return self._duplicate_customer_dict(row) if row else None

    def find_by_aadhaar(self, aadhaar: str, *, exclude_customer_id: int | None = None) -> dict | None:
        digits = re.sub(r"\D", "", aadhaar or "")
        if len(digits) != 12:
            return None
        sql = """
            SELECT TOP 1 CustomerID, CustomerName, MobileNumber, PANNumber, AadhaarNumber, CustomerGroup
            FROM CustomerMaster
            WHERE REPLACE(AadhaarNumber, ' ', '') = :aadhaar
              AND CustomerStatus <> N'Inactive'
        """
        params = {"aadhaar": digits}
        if exclude_customer_id:
            sql += " AND CustomerID <> :exclude_id"
            params["exclude_id"] = exclude_customer_id
        row = self.session.execute(text(sql), params).mappings().first()
        return self._duplicate_customer_dict(row) if row else None

    def find_by_mobile(self, mobile: str, *, exclude_customer_id: int | None = None) -> list[dict]:
        normalized = self._normalize_mobile(mobile)
        if not normalized:
            return []
        sql = """
            SELECT CustomerID, CustomerName, MobileNumber, PANNumber, AadhaarNumber, CustomerGroup
            FROM CustomerMaster
            WHERE MobileNumber = :mobile
              AND CustomerStatus <> N'Inactive'
        """
        params = {"mobile": normalized}
        if exclude_customer_id:
            sql += " AND CustomerID <> :exclude_id"
            params["exclude_id"] = exclude_customer_id
        rows = self.session.execute(text(sql), params).mappings().all()
        return [self._duplicate_customer_dict(row) for row in rows]

    def find_by_email(self, email: str, *, exclude_customer_id: int | None = None) -> list[dict]:
        normalized = (email or "").strip().lower()
        if not normalized:
            return []
        sql = """
            SELECT CustomerID, CustomerName, MobileNumber, PANNumber, AadhaarNumber, CustomerGroup
            FROM CustomerMaster
            WHERE LOWER(LTRIM(RTRIM(EmailID))) = :email
              AND CustomerStatus <> N'Inactive'
        """
        params = {"email": normalized}
        if exclude_customer_id:
            sql += " AND CustomerID <> :exclude_id"
            params["exclude_id"] = exclude_customer_id
        rows = self.session.execute(text(sql), params).mappings().all()
        return [self._duplicate_customer_dict(row) for row in rows]

    def get_portal_auth(self, customer_id: int) -> dict | None:
        """Return portal auth fields for a customer (parameterized)."""
        self.ensure_schema()
        row = (
            self.session.execute(
                text(
                    """
                    SELECT
                        CustomerID,
                        CustomerName,
                        MobileNumber,
                        EmailID,
                        PANNumber,
                        AadhaarNumber,
                        CustomerStatus,
                        PortalPassword,
                        PasswordChanged,
                        LastLogin,
                        LastPasswordChange,
                        PasswordResetDate,
                        FailedLoginCount,
                        AccountLocked
                    FROM dbo.CustomerMaster
                    WHERE CustomerID = :id
                    """
                ),
                {"id": int(customer_id)},
            )
            .mappings()
            .first()
        )
        if not row:
            return None
        return {
            "customer_id": int(row["CustomerID"]),
            "customer_name": row.get("CustomerName") or "",
            "mobile_number": row.get("MobileNumber") or "",
            "email_id": row.get("EmailID") or "",
            "pan_number": row.get("PANNumber") or "",
            "aadhaar_number": row.get("AadhaarNumber") or "",
            "customer_status": row.get("CustomerStatus") or "",
            "portal_password": row.get("PortalPassword") or "",
            "password_changed": bool(row.get("PasswordChanged")),
            "last_login": row.get("LastLogin"),
            "last_password_change": row.get("LastPasswordChange"),
            "password_reset_date": row.get("PasswordResetDate"),
            "failed_login_count": int(row.get("FailedLoginCount") or 0),
            "account_locked": bool(row.get("AccountLocked")),
        }

    def update_portal_login_success(self, customer_id: int) -> None:
        self.ensure_schema()
        self.session.execute(
            text(
                """
                UPDATE dbo.CustomerMaster
                SET LastLogin = :now,
                    FailedLoginCount = 0,
                    AccountLocked = 0
                WHERE CustomerID = :id
                """
            ),
            {"now": datetime.utcnow(), "id": int(customer_id)},
        )
        self.session.flush()

    def update_portal_login_failure(self, customer_id: int, *, lock: bool = False) -> None:
        self.ensure_schema()
        self.session.execute(
            text(
                """
                UPDATE dbo.CustomerMaster
                SET FailedLoginCount = ISNULL(FailedLoginCount, 0) + 1,
                    AccountLocked = CASE WHEN :lock = 1 THEN 1 ELSE AccountLocked END
                WHERE CustomerID = :id
                """
            ),
            {"id": int(customer_id), "lock": 1 if lock else 0},
        )
        self.session.flush()

    def reset_portal_password(self, customer_id: int, password_hash: str) -> None:
        """Reset portal password to the provided hash (default Admin@123)."""
        self.ensure_schema()
        self.session.execute(
            text(
                """
                UPDATE dbo.CustomerMaster
                SET PortalPassword = :pwd,
                    PasswordChanged = 0,
                    PasswordResetDate = :now,
                    FailedLoginCount = 0,
                    AccountLocked = 0
                WHERE CustomerID = :id
                """
            ),
            {
                "pwd": password_hash,
                "now": datetime.utcnow(),
                "id": int(customer_id),
            },
        )
        self.session.flush()

    def change_portal_password(self, customer_id: int, password_hash: str) -> None:
        self.ensure_schema()
        self.session.execute(
            text(
                """
                UPDATE dbo.CustomerMaster
                SET PortalPassword = :pwd,
                    PasswordChanged = 1,
                    LastPasswordChange = :now,
                    FailedLoginCount = 0,
                    AccountLocked = 0
                WHERE CustomerID = :id
                """
            ),
            {
                "pwd": password_hash,
                "now": datetime.utcnow(),
                "id": int(customer_id),
            },
        )
        self.session.flush()

    def log_portal_login_attempt(
        self,
        *,
        customer_id: int | None,
        user_id_input: str,
        detected_type: str | None,
        attempt_result: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        self.ensure_schema()
        self.session.execute(
            text(
                """
                INSERT INTO dbo.CustomerPortalLoginLog (
                    CustomerID, UserIdInput, DetectedType, AttemptResult, IpAddress, UserAgent, CreatedDate
                )
                VALUES (
                    :customer_id, :user_id_input, :detected_type, :attempt_result, :ip_address, :user_agent, :created
                )
                """
            ),
            {
                "customer_id": customer_id,
                "user_id_input": (user_id_input or "")[:255],
                "detected_type": (detected_type or None),
                "attempt_result": (attempt_result or "unknown")[:40],
                "ip_address": (ip_address or None),
                "user_agent": ((user_agent or "")[:500] or None),
                "created": datetime.utcnow(),
            },
        )
        self.session.flush()

    def list_income_expense_work_ids(self, customer_id: int) -> list[int]:
        """WorkMaster IDs linked for Income/Expense use (read-only on WorkMaster)."""
        self.ensure_schema()
        rows = self.session.execute(
            text(
                """
                SELECT l.WorkID
                FROM dbo.CustomerIncomeExpenseWorkLink l
                INNER JOIN dbo.WorkMaster w ON w.WorkID = l.WorkID
                WHERE l.CustomerID = :cid
                  AND ISNULL(w.ActiveStatus, 1) = 1
                ORDER BY w.WorkName
                """
            ),
            {"cid": customer_id},
        ).all()
        return [int(r[0]) for r in rows]

    def replace_income_expense_work_ids(self, customer_id: int, work_ids: list[int]) -> None:
        """Replace Income/Expense work links for a customer."""
        self.ensure_schema()
        self.session.execute(
            text("DELETE FROM dbo.CustomerIncomeExpenseWorkLink WHERE CustomerID = :cid"),
            {"cid": customer_id},
        )
        for wid in work_ids:
            self.session.execute(
                text(
                    """
                    INSERT INTO dbo.CustomerIncomeExpenseWorkLink (CustomerID, WorkID)
                    VALUES (:cid, :wid)
                    """
                ),
                {"cid": customer_id, "wid": int(wid)},
            )
        self.session.flush()
