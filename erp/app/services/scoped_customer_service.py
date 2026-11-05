"""Customer creation used only by Money In-Out, Follow-up and Miscellaneous flows."""

from __future__ import annotations

import re
from datetime import date

from sqlalchemy import text

from app.customer_master.constants import CUSTOMER_TYPES, GENDERS
from app.repositories.customer_repository import CustomerRepository
from app.services.chart_account_service import ChartAccountService
from app.services.chart_group_service import ChartGroupService
from app.services.customer_group_service import CustomerGroupService
from app.utils.db_session import persist


class ScopedCustomerService:
    """Create a customer with the compact form shared by the scoped activity screens."""

    def __init__(self, repository: CustomerRepository | None = None):
        self.repository = repository or CustomerRepository()

    def create(self, payload: dict) -> dict:
        self.repository.ensure_schema()

        name = str(payload.get("customer_name") or payload.get("CustomerName") or "").strip()
        group = str(payload.get("customer_group") or payload.get("CustomerGroup") or "").strip().upper()
        customer_type = str(payload.get("customer_type") or payload.get("CustomerType") or "").strip()
        gender = str(payload.get("gender") or payload.get("Gender") or "").strip()
        raw_group_id = payload.get("group_id") or payload.get("chart_group_id") or payload.get("GroupID")
        if not name:
            raise ValueError("Customer name is required.")
        if group not in {str(row["code"]).strip().upper() for row in CustomerGroupService().list_active_groups()}:
            raise ValueError("Select a valid customer group.")
        if not customer_type or customer_type not in CUSTOMER_TYPES:
            raise ValueError("Select a valid customer type.")
        if not gender or gender not in GENDERS:
            raise ValueError("Select a valid gender.")
        try:
            group_id = int(raw_group_id)
        except (TypeError, ValueError):
            raise ValueError("Select a Chart of Account Group.") from None
        active_chart_ids = {
            int(row["group_id"])
            for row in ChartGroupService().list_active_for_dropdown()
            if row.get("group_id")
        }
        if group_id not in active_chart_ids:
            raise ValueError("Select a valid Chart of Account Group.")

        mobile_raw = str(payload.get("mobile_number") or payload.get("MobileNumber") or "").strip()
        mobile = self.repository._normalize_mobile(mobile_raw)
        if mobile_raw and len(mobile) != 10:
            raise ValueError("Enter a valid 10-digit mobile number.")
        if mobile:
            duplicate = self.repository.session.execute(
                text(
                    """
                    SELECT TOP 1 CustomerID, CustomerName, MobileNumber
                    FROM dbo.CustomerMaster
                    WHERE RIGHT(
                        REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
                            ISNULL(MobileNumber, N''), N'+', N''), N' ', N''), N'-', N''),
                            N'(', N''), N')', N''), N'.', N''), N'/', N''), NCHAR(9), N''),
                        10
                    ) = :mobile
                      AND ISNULL(CustomerStatus, N'Active') NOT IN (N'Inactive', N'Rejected', N'Deleted')
                    """
                ),
                {"mobile": mobile},
            ).mappings().first()
            if duplicate:
                raise ValueError(
                    f"Mobile number already exists for customer {duplicate['CustomerName']} "
                    f"(ID {duplicate['CustomerID']})."
                )

        email = str(payload.get("email_id") or payload.get("EmailID") or "").strip()
        if email and ("@" not in email or "." not in email.split("@")[-1]):
            raise ValueError("Enter a valid email address.")
        aadhaar_raw = str(payload.get("aadhaar_number") or payload.get("AadhaarNumber") or "").strip()
        aadhaar = re.sub(r"\D", "", aadhaar_raw)
        if aadhaar_raw and len(aadhaar) != 12:
            raise ValueError("Aadhaar must contain 12 digits.")
        pincode_raw = str(payload.get("pincode") or payload.get("Pincode") or "").strip()
        pincode = re.sub(r"\D", "", pincode_raw)
        if pincode_raw and len(pincode) != 6:
            raise ValueError("Pincode must contain 6 digits.")
        gst_number = str(payload.get("gst_number") or payload.get("GSTNumber") or "").strip().upper()
        if gst_number and len(gst_number) != 15:
            raise ValueError("GST number must contain 15 characters.")
        since_raw = str(
            payload.get("customer_since_date") or payload.get("CustomerSinceDate") or ""
        ).strip()
        if since_raw:
            try:
                date.fromisoformat(since_raw[:10])
            except ValueError as exc:
                raise ValueError("Enter a valid Customer Since Date.") from exc

        save_payload = {
            "customer_group": group,
            "customer_type": customer_type,
            "customer_name": name[:255],
            "gender": gender,
            "mobile_number": mobile or None,
            "email_id": email or None,
            "aadhaar_number": aadhaar or None,
            "pincode": pincode or None,
            "post_office": str(payload.get("post_office") or payload.get("PostOffice") or "").strip()[:100] or None,
            "district": str(payload.get("district") or payload.get("District") or "").strip()[:100] or None,
            "state": str(payload.get("state") or payload.get("State") or "").strip()[:100] or None,
            "country": (str(payload.get("country") or payload.get("Country") or "India").strip() or "India")[:100],
            "gst_number": gst_number or None,
            "customer_introduced_by": str(
                payload.get("customer_introduced_by") or payload.get("CustomerIntroducedBy") or ""
            ).strip()[:200] or None,
            "customer_since_date": since_raw[:10] or None,
            "customer_status": "Active",
        }

        def _write() -> dict:
            return self.repository.save_full(save_payload)

        customer = persist(_write)
        customer_id = int(customer.get("customer_id") or 0)
        if not customer_id:
            raise ValueError("Customer was saved but its ID could not be read.")
        ChartAccountService().assign_customer_group(customer_id, {"group_ids": [group_id]})
        customer["group_id"] = group_id
        return customer
