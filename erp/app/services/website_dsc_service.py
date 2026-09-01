"""Website DSC applications from jtcsxpert.com."""

from __future__ import annotations

import logging
import re
import secrets
from datetime import datetime
from pathlib import Path

from flask import current_app
from flask_mail import Message
from sqlalchemy import text

from app.extensions import db, mail
from app.models.auth import CompanyProfile
from app.models.website_dsc import WebsiteDscApplication
from app.repositories.transaction_repository import MasterRepository
from app.services import dsc_documents

logger = logging.getLogger(__name__)

PROFESSIONAL_CHARGE = 500.0
DSC_TYPES = {
    "class3_sign": "Class 3 Signing",
    "class3_combo": "Class 3 Combo (Signing + Encryption)",
    "dgft": "DGFT",
}
VALID_YEARS = {1, 2, 3}
APPLICANT_TYPES = {"individual", "organization"}
PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")

_SCHEMA_SQL = """
IF OBJECT_ID(N'dbo.WebsiteDscApplication', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.WebsiteDscApplication (
        ApplicationID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        ReferenceNo NVARCHAR(40) NOT NULL,
        DscType NVARCHAR(80) NOT NULL,
        ValidityYears INT NOT NULL,
        ApplicantType NVARCHAR(20) NOT NULL,
        FullName NVARCHAR(160) NOT NULL,
        Pan NVARCHAR(10) NOT NULL,
        AadhaarLast4 NVARCHAR(4) NULL,
        Mobile NVARCHAR(15) NOT NULL,
        Email NVARCHAR(160) NOT NULL,
        Address NVARCHAR(400) NOT NULL,
        OrganizationName NVARCHAR(200) NULL,
        OrganizationId NVARCHAR(80) NULL,
        AuthLetterPath NVARCHAR(400) NULL,
        AuthLetterName NVARCHAR(180) NULL,
        Amount DECIMAL(18, 2) NOT NULL CONSTRAINT DF_WebsiteDsc_Amount DEFAULT (500),
        PayableAmount DECIMAL(18, 2) NULL,
        PayMethod NVARCHAR(40) NULL,
        UtrNumber NVARCHAR(40) NULL,
        PaymentStatus NVARCHAR(30) NOT NULL CONSTRAINT DF_WebsiteDsc_Pay DEFAULT (N'pending'),
        IsPaid BIT NOT NULL CONSTRAINT DF_WebsiteDsc_IsPaid DEFAULT (0),
        ReviewStatus NVARCHAR(40) NOT NULL CONSTRAINT DF_WebsiteDsc_Review DEFAULT (N'New'),
        CustomerID INT NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_WebsiteDsc_Created DEFAULT (SYSUTCDATETIME()),
        ModifiedDate DATETIME2 NULL,
        CONSTRAINT UX_WebsiteDsc_Reference UNIQUE (ReferenceNo)
    );
END
"""

_MENU_SQL = """
DECLARE @ParentID INT;
DECLARE @AdminRoles NVARCHAR(80) = N'Administrator,Admin,Manager,Reception,Operator';

SELECT TOP 1 @ParentID = MenuID
FROM dbo.MenuMaster
WHERE MenuName = N'Admin Role' AND ParentMenuID IS NULL
ORDER BY MenuID;

IF @ParentID IS NOT NULL
AND NOT EXISTS (
    SELECT 1 FROM dbo.MenuMaster
    WHERE MenuURL = N'/admin/dsc-orders'
)
BEGIN
    INSERT INTO dbo.MenuMaster (
        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
        Description, IsActive, RoleName
    )
    VALUES (
        @ParentID, N'DSC Applications', N'bi-pen', N'/admin/dsc-orders', 69,
        N'Website Digital Signature Certificate applications', 1, @AdminRoles
    );
END
"""


def _clean(value, limit: int = 160) -> str:
    return " ".join(str(value or "").split())[:limit]


def _mobile(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


def _pan(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()[:10]


def _aadhaar_last4(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits[-4:] if len(digits) >= 4 else ""


class WebsiteDscService:
    def ensure_schema(self) -> None:
        db.session.execute(text(_SCHEMA_SQL))
        db.session.execute(text(_MENU_SQL))
        db.session.commit()
        dsc_documents.ensure_dsc_doc_schema()

    def options(self) -> dict:
        count = 0
        try:
            count = dsc_documents.customer_master_count()
        except Exception:
            count = 0
        return {
            "ok": True,
            "professional_charge": PROFESSIONAL_CHARGE,
            "dsc_types": [{"code": k, "label": v} for k, v in DSC_TYPES.items()],
            "years": sorted(VALID_YEARS),
            "applicant_types": [
                {"code": "individual", "label": "Individual"},
                {"code": "organization", "label": "Organization"},
            ],
            "customer_count": count,
            "dsc_issued": count,
        }

    def list_applications(self, limit: int = 300) -> list[dict]:
        self.ensure_schema()
        rows = (
            db.session.query(WebsiteDscApplication)
            .order_by(WebsiteDscApplication.CreatedDate.desc())
            .limit(limit)
            .all()
        )
        return [self._row(row) for row in rows]

    def get_by_reference(self, reference_no: str) -> WebsiteDscApplication | None:
        ref = _clean(reference_no, 40).upper()
        if not ref:
            return None
        return (
            db.session.query(WebsiteDscApplication)
            .filter(WebsiteDscApplication.ReferenceNo == ref)
            .one_or_none()
        )

    def upsert(self, data: dict, *, paid: bool = False) -> dict:
        self.ensure_schema()
        parsed = self._validate(data)
        reference = _clean(data.get("reference_no"), 40).upper() or self._new_reference()
        existing = self.get_by_reference(reference)
        if existing:
            self._apply(existing, parsed, data)
            if paid or str(data.get("payment_status") or "").lower() in {"paid", "upi_paid"} or data.get("paid"):
                existing.IsPaid = True
                existing.PaymentStatus = "paid"
                existing.PayMethod = _clean(data.get("pay_method"), 40) or existing.PayMethod or "upi"
                existing.UtrNumber = _clean(data.get("utr_number") or data.get("utr"), 40) or existing.UtrNumber
            existing.ModifiedDate = datetime.utcnow()
            db.session.commit()
            if existing.IsPaid:
                self._notify(existing)
            return self._public(existing)
        customer_id = None
        try:
            customer = MasterRepository().find_or_create_customer(parsed["full_name"], parsed["mobile"])
            customer_id = customer.CustomerID
        except Exception:
            db.session.rollback()
            logger.warning("DSC customer link skipped", exc_info=True)
        row = WebsiteDscApplication(ReferenceNo=reference, CustomerID=customer_id)
        self._apply(row, parsed, data)
        row.CreatedDate = datetime.utcnow()
        if paid or str(data.get("payment_status") or "").lower() in {"paid", "upi_paid"} or data.get("paid"):
            row.IsPaid = True
            row.PaymentStatus = "paid"
        else:
            row.IsPaid = False
            row.PaymentStatus = "pending"
        db.session.add(row)
        db.session.commit()
        if row.IsPaid:
            self._notify(row)
        return self._public(row)

    def save_auth_letter(self, reference_no: str, file_storage) -> dict:
        return self.save_document(reference_no, "auth_letter", file_storage)

    def save_document(self, reference_no: str, kind: str, file_storage) -> dict:
        row = self.get_by_reference(reference_no)
        if row is None:
            raise ValueError("DSC application not found.")
        meta = dsc_documents.DSC_DOC_KINDS.get((kind or "").strip().lower())
        if not meta:
            raise ValueError("Unknown DSC document type.")
        folder = Path(current_app.config["UPLOAD_FOLDER"]) / "dsc_applications"
        old_path = (getattr(row, meta["app_path"], None) or "").strip()
        path, name = dsc_documents._save_upload(folder, f"{row.ReferenceNo}_{kind}", file_storage)
        setattr(row, meta["app_path"], path)
        setattr(row, meta["app_name"], name)
        row.ModifiedDate = datetime.utcnow()
        db.session.commit()
        dsc_documents._delete_stored_file_if_replaced(old_path, path)
        if row.CustomerID:
            try:
                dsc_documents.ensure_dsc_doc_schema()
                old_cm = db.session.execute(
                    text(
                        f"SELECT {meta['path_col']} AS DocPath FROM dbo.CustomerMaster WHERE CustomerID = :id"
                    ),
                    {"id": int(row.CustomerID)},
                ).mappings().first()
                db.session.execute(
                    text(
                        f"UPDATE dbo.CustomerMaster SET {meta['path_col']} = :path, {meta['name_col']} = :name, "
                        "ModifiedDate = SYSUTCDATETIME() WHERE CustomerID = :id"
                    ),
                    {"path": path, "name": name, "id": int(row.CustomerID)},
                )
                db.session.commit()
                dsc_documents._delete_stored_file_if_replaced((old_cm or {}).get("DocPath") or "", path)
                dsc_documents._mirror_crm_document(int(row.CustomerID), meta["label"], name, path, "Website DSC")
            except Exception:
                db.session.rollback()
                logger.warning("Customer Master DSC document sync skipped", exc_info=True)
        return self._public(row)

    def invoice_html(self, reference_no: str) -> str:
        row = self.get_by_reference(reference_no)
        if row is None or not row.IsPaid:
            raise ValueError("Invoice is available after payment.")
        amount = float(row.PayableAmount or row.Amount or PROFESSIONAL_CHARGE)
        org = f"<p>Organization: {self._esc(row.OrganizationName or '')} ({self._esc(row.OrganizationId or '')})</p>" if row.ApplicantType == "organization" else ""
        return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Invoice {self._esc(row.ReferenceNo)}</title>
<style>
body{{font-family:Arial,sans-serif;max-width:720px;margin:24px auto;padding:0 16px;color:#111}}
h1{{font-size:1.3rem}} table{{width:100%;border-collapse:collapse;margin-top:16px}}
th,td{{border:1px solid #ddd;padding:8px;text-align:left}} .right{{text-align:right}}
@media print {{ .noprint {{ display:none }} }}
</style></head><body>
<p class="noprint"><button onclick="window.print()">Print / Save PDF</button></p>
<h1>JTCS — DSC Professional Invoice</h1>
<p>Joshi Tax Consultancy &amp; Services, Haldwani, Uttarakhand</p>
<p>Invoice / Reference: <strong>{self._esc(row.ReferenceNo)}</strong><br>
Date: {row.CreatedDate.strftime("%d/%m/%Y") if row.CreatedDate else ""}<br>
Applicant: {self._esc(row.FullName)} ({self._esc(row.ApplicantType)})<br>
PAN: {self._esc(row.Pan)} &nbsp; Mobile: {self._esc(row.Mobile)}<br>
Email: {self._esc(row.Email)}</p>
{org}
<table>
<tr><th>Description</th><th class="right">Amount</th></tr>
<tr><td>Digital Signature Certificate — {self._esc(row.DscType)}, {int(row.ValidityYears)} year(s)<br>Professional charges</td><td class="right">₹ {amount:.2f}</td></tr>
<tr><th>Total payable</th><th class="right">₹ {amount:.2f}</th></tr>
</table>
<p>Payment: {self._esc(row.PayMethod or "UPI")} &nbsp; UTR: {self._esc(row.UtrNumber or "—")}</p>
<p>This is a professional-charges receipt. Government / token charges, if any, are extra and billed later.</p>
</body></html>"""

    def template_path(self) -> Path:
        return Path(current_app.root_path) / "static" / "templates" / "dsc-authorization-letter.html"

    def _validate(self, data: dict) -> dict:
        dsc_code = _clean(data.get("dsc_type") or data.get("dsc_type_code"), 40).lower()
        if dsc_code not in DSC_TYPES:
            raise ValueError("Please select DSC type.")
        try:
            years = int(data.get("validity_years") or data.get("year") or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("Please select DSC year.") from exc
        if years not in VALID_YEARS:
            raise ValueError("Please select 1, 2 or 3 years.")
        applicant = _clean(data.get("applicant_type"), 20).lower()
        if applicant not in APPLICANT_TYPES:
            raise ValueError("Please choose Individual or Organization.")
        name = _clean(data.get("full_name") or data.get("name"))
        if len(name) < 2:
            raise ValueError("Please enter the applicant name.")
        pan = _pan(data.get("pan") or "")
        if not PAN_RE.match(pan):
            raise ValueError("Please enter a valid PAN.")
        aadhaar_digits = "".join(ch for ch in str(data.get("aadhaar") or "") if ch.isdigit())
        if len(aadhaar_digits) != 12:
            raise ValueError("Please enter a valid 12-digit Aadhaar number.")
        mobile = _mobile(data.get("mobile") or "")
        if len(mobile) != 10 or mobile[0] not in "6789":
            raise ValueError("Please enter a valid 10-digit mobile number.")
        email = _clean(data.get("email"), 160)
        if "@" not in email or "." not in email:
            raise ValueError("Please enter a valid email.")
        address = _clean(data.get("address"), 400)
        if len(address) < 8:
            raise ValueError("Please enter the full address.")
        org_name = _clean(data.get("organization_name"), 200) if applicant == "organization" else ""
        org_id = _clean(data.get("organization_id"), 80) if applicant == "organization" else ""
        org_address = _clean(data.get("organization_address"), 400) if applicant == "organization" else ""
        if applicant == "organization":
            if len(org_name) < 2:
                raise ValueError("Please enter the organization name.")
            if len(org_id) < 3:
                raise ValueError("Please enter the organization ID.")
            if len(org_address) < 8:
                raise ValueError("Please enter the organization address.")
        return {
            "dsc_type": DSC_TYPES[dsc_code],
            "dsc_code": dsc_code,
            "years": years,
            "applicant": applicant,
            "full_name": name,
            "pan": pan,
            "aadhaar_last4": _aadhaar_last4(aadhaar_digits),
            "mobile": mobile,
            "email": email,
            "address": address,
            "organization_name": org_name or None,
            "organization_id": org_id or None,
            "organization_address": org_address or None,
        }

    def _apply(self, row: WebsiteDscApplication, parsed: dict, data: dict) -> None:
        row.DscType = parsed["dsc_type"]
        row.ValidityYears = parsed["years"]
        row.ApplicantType = parsed["applicant"]
        row.FullName = parsed["full_name"]
        row.Pan = parsed["pan"]
        row.AadhaarLast4 = parsed["aadhaar_last4"] or None
        row.Mobile = parsed["mobile"]
        row.Email = parsed["email"]
        row.Address = parsed["address"]
        row.OrganizationName = parsed["organization_name"]
        row.OrganizationId = parsed["organization_id"]
        if hasattr(row, "OrganizationAddress"):
            row.OrganizationAddress = parsed.get("organization_address")
        row.Amount = PROFESSIONAL_CHARGE
        try:
            row.PayableAmount = float(data.get("payable_amount") or PROFESSIONAL_CHARGE)
        except (TypeError, ValueError):
            row.PayableAmount = PROFESSIONAL_CHARGE
        row.PayMethod = _clean(data.get("pay_method"), 40) or row.PayMethod
        row.UtrNumber = _clean(data.get("utr_number") or data.get("utr"), 40) or row.UtrNumber
        row.ReviewStatus = row.ReviewStatus or "New"

    def _new_reference(self) -> str:
        day = datetime.utcnow().strftime("%Y%m%d")
        return f"DSC-{day}-{secrets.token_hex(2).upper()}"

    def _row(self, row: WebsiteDscApplication) -> dict:
        return {
            "application_id": row.ApplicationID,
            "reference_no": row.ReferenceNo,
            "dsc_type": row.DscType,
            "validity_years": row.ValidityYears,
            "applicant_type": row.ApplicantType,
            "full_name": row.FullName,
            "pan": row.Pan,
            "mobile": row.Mobile,
            "email": row.Email,
            "address": row.Address,
            "organization_name": row.OrganizationName or "",
            "organization_id": row.OrganizationId or "",
            "organization_address": getattr(row, "OrganizationAddress", None) or "",
            "auth_letter_name": row.AuthLetterName or "",
            "pan_doc_name": getattr(row, "PanDocName", None) or "",
            "aadhaar_doc_name": getattr(row, "AadhaarDocName", None) or "",
            "org_id_doc_name": getattr(row, "OrgIdDocName", None) or "",
            "amount": float(row.Amount or PROFESSIONAL_CHARGE),
            "payable_amount": float(row.PayableAmount or row.Amount or PROFESSIONAL_CHARGE),
            "pay_method": row.PayMethod or "",
            "utr_number": row.UtrNumber or "",
            "payment_status": row.PaymentStatus,
            "is_paid": bool(row.IsPaid),
            "review_status": row.ReviewStatus,
            "created_date": row.CreatedDate.strftime("%d/%m/%Y %H:%M") if row.CreatedDate else "",
        }

    def _public(self, row: WebsiteDscApplication) -> dict:
        data = self._row(row)
        data["ok"] = True
        data["professional_charge"] = PROFESSIONAL_CHARGE
        data["message"] = (
            "Payment received. Reference Number: " + row.ReferenceNo
            if row.IsPaid
            else "Application saved. Continue to payment."
        )
        return data

    @staticmethod
    def _esc(value: str) -> str:
        return (
            str(value or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def _notify(self, row: WebsiteDscApplication) -> None:
        title = f"DSC paid {row.ReferenceNo}"
        body = (
            f"Reference: {row.ReferenceNo}\n"
            f"Name: {row.FullName}\n"
            f"Type: {row.ApplicantType}\n"
            f"DSC: {row.DscType} / {row.ValidityYears}y\n"
            f"Mobile: {row.Mobile}\n"
            f"PAN: {row.Pan}\n"
            f"Payable: ₹{row.PayableAmount or row.Amount}\n"
            f"UTR: {row.UtrNumber or '-'}"
        )
        try:
            from app.modules.notification.services import NotificationService

            NotificationService().notify_roles_or_all(
                notification_type="Payment",
                title=title,
                message=body.replace("\n", " · "),
                link_url="/admin/dsc-orders",
                priority="High",
                entity_type="WebsiteDscApplication",
                entity_id=row.ApplicationID,
            )
        except Exception:
            logger.exception("DSC in-app notification failed")
        company = db.session.query(CompanyProfile).first()
        email_to = (company.Email if company else None) or current_app.config.get("MAIL_DEFAULT_SENDER")
        if email_to:
            try:
                sender = current_app.config.get("MAIL_DEFAULT_SENDER") or current_app.config.get("MAIL_USERNAME")
                mail.send(Message(subject=title, recipients=[str(email_to)], body=body, sender=sender))
            except Exception:
                logger.exception("DSC email notification failed")
