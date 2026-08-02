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
        ):
            self.session.execute(text(stmt))
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
            values["OpeningBalanceDrCr"] = "Dr"
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
        return self.get_full(int(new_id))

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
