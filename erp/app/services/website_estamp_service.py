"""Website e-Stamp orders: paid requests only appear in Stamp Orders."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime

from flask import current_app
from flask_mail import Message
from sqlalchemy import text

from app.extensions import db, mail
from app.models.auth import CompanyProfile
from app.models.website_estamp import WebsiteEStampOrder
from app.repositories.transaction_repository import MasterRepository
from app.services.website_estamp_articles import article_by_code, article_display, public_articles

logger = logging.getLogger(__name__)

_SCHEMA_SQL = """
IF OBJECT_ID(N'dbo.WebsiteEStampOrder', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.WebsiteEStampOrder (
        OrderID INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        ReferenceNo NVARCHAR(40) NOT NULL,
        FullName NVARCHAR(160) NOT NULL,
        FatherOrHusbandName NVARCHAR(160) NULL,
        SecondPartyName NVARCHAR(160) NULL,
        SecondPartyFatherOrHusbandName NVARCHAR(160) NULL,
        Mobile NVARCHAR(15) NOT NULL,
        ArticleCode NVARCHAR(40) NOT NULL,
        ArticleLabel NVARCHAR(240) NULL,
        Amount DECIMAL(18, 2) NOT NULL,
        PayableAmount DECIMAL(18, 2) NULL,
        DeliveryMode NVARCHAR(20) NULL,
        HouseNo NVARCHAR(80) NULL,
        Gali NVARCHAR(160) NULL,
        Mohalla NVARCHAR(160) NULL,
        Landmark NVARCHAR(200) NULL,
        AddressNote NVARCHAR(300) NULL,
        GeoAddress NVARCHAR(400) NULL,
        LocationUrl NVARCHAR(500) NULL,
        PayMethod NVARCHAR(40) NULL,
        UtrNumber NVARCHAR(40) NULL,
        PaymentStatus NVARCHAR(30) NOT NULL CONSTRAINT DF_WebsiteEStamp_Pay DEFAULT (N'paid'),
        IsPaid BIT NOT NULL CONSTRAINT DF_WebsiteEStamp_IsPaid DEFAULT (1),
        ReviewStatus NVARCHAR(40) NOT NULL CONSTRAINT DF_WebsiteEStamp_Review DEFAULT (N'New'),
        ReviewNotes NVARCHAR(500) NULL,
        CustomerID INT NULL,
        CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_WebsiteEStamp_Created DEFAULT (SYSUTCDATETIME()),
        ModifiedDate DATETIME2 NULL,
        CONSTRAINT UX_WebsiteEStamp_Reference UNIQUE (ReferenceNo)
    );
END
"""

_COLUMNS_SQL = """
IF OBJECT_ID(N'dbo.WebsiteEStampOrder', N'U') IS NOT NULL
BEGIN
    IF COL_LENGTH(N'dbo.WebsiteEStampOrder', N'IsPaid') IS NULL
        ALTER TABLE dbo.WebsiteEStampOrder ADD IsPaid BIT NOT NULL CONSTRAINT DF_WebsiteEStamp_IsPaid DEFAULT (1);
    IF COL_LENGTH(N'dbo.WebsiteEStampOrder', N'PayMethod') IS NULL
        ALTER TABLE dbo.WebsiteEStampOrder ADD PayMethod NVARCHAR(40) NULL;
    IF COL_LENGTH(N'dbo.WebsiteEStampOrder', N'PaymentStatus') IS NULL
        ALTER TABLE dbo.WebsiteEStampOrder ADD PaymentStatus NVARCHAR(30) NULL;
    IF COL_LENGTH(N'dbo.WebsiteEStampOrder', N'PayableAmount') IS NULL
        ALTER TABLE dbo.WebsiteEStampOrder ADD PayableAmount DECIMAL(18, 2) NULL;
    IF COL_LENGTH(N'dbo.WebsiteEStampOrder', N'SecondPartyName') IS NULL
        ALTER TABLE dbo.WebsiteEStampOrder ADD SecondPartyName NVARCHAR(160) NULL;
    IF COL_LENGTH(N'dbo.WebsiteEStampOrder', N'SecondPartyFatherOrHusbandName') IS NULL
        ALTER TABLE dbo.WebsiteEStampOrder ADD SecondPartyFatherOrHusbandName NVARCHAR(160) NULL;
    IF COL_LENGTH(N'dbo.WebsiteEStampOrder', N'UtrNumber') IS NULL
        ALTER TABLE dbo.WebsiteEStampOrder ADD UtrNumber NVARCHAR(40) NULL;
    IF COL_LENGTH(N'dbo.WebsiteEStampOrder', N'ConsiderationPrice') IS NULL
        ALTER TABLE dbo.WebsiteEStampOrder ADD ConsiderationPrice DECIMAL(18, 2) NULL;
    IF COL_LENGTH(N'dbo.WebsiteEStampOrder', N'Description') IS NULL
        ALTER TABLE dbo.WebsiteEStampOrder ADD Description NVARCHAR(50) NULL;
    IF COL_LENGTH(N'dbo.WebsiteEStampOrder', N'PoiDocumentType') IS NULL
        ALTER TABLE dbo.WebsiteEStampOrder ADD PoiDocumentType NVARCHAR(40) NULL;
    IF COL_LENGTH(N'dbo.WebsiteEStampOrder', N'PoiDocPath') IS NULL
        ALTER TABLE dbo.WebsiteEStampOrder ADD PoiDocPath NVARCHAR(400) NULL;
    IF COL_LENGTH(N'dbo.WebsiteEStampOrder', N'PoiDocName') IS NULL
        ALTER TABLE dbo.WebsiteEStampOrder ADD PoiDocName NVARCHAR(200) NULL;
    IF COL_LENGTH(N'dbo.WebsiteEStampOrder', N'PaymentConfirmed') IS NULL
        ALTER TABLE dbo.WebsiteEStampOrder ADD PaymentConfirmed NVARCHAR(10) NULL;
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
    WHERE MenuURL = N'/admin/estamp-orders'
)
BEGIN
    INSERT INTO dbo.MenuMaster (
        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
        Description, IsActive, RoleName
    )
    VALUES (
        @ParentID, N'e-Stamp Orders', N'bi-postage', N'/admin/estamp-orders', 68,
        N'Paid website e-Stamp purchase requests', 1, @AdminRoles
    );
END
ELSE IF EXISTS (SELECT 1 FROM dbo.MenuMaster WHERE MenuURL = N'/admin/estamp-orders')
BEGIN
    UPDATE dbo.MenuMaster
    SET MenuName = N'e-Stamp Orders',
        IsActive = 1,
        Description = N'Paid website e-Stamp purchase requests'
    WHERE MenuURL = N'/admin/estamp-orders';
END
"""


def _clean(value, limit: int = 160) -> str:
    return " ".join(str(value or "").split())[:limit]


POI_LABELS = {
    "aadhaar": "Aadhaar Card",
    "pan": "PAN Card",
    "driving_licence": "Driving Licence",
    "voter_id": "Voter ID (EPIC)",
    "passport": "Passport",
    "ration_card": "Ration Card",
    "govt_photo_id": "Government Photo ID",
    "bank_passbook": "Bank Passbook",
    "pension_card": "Pension Card / PPO",
    "nrega_job_card": "NREGA Job Card",
}


def _mobile(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


class WebsiteEStampService:
    def ensure_schema(self) -> None:
        db.session.execute(text(_SCHEMA_SQL))
        db.session.execute(text(_COLUMNS_SQL))
        db.session.execute(text(_MENU_SQL))
        db.session.commit()

    def articles(self) -> list[dict]:
        return public_articles()

    def list_paid(self, limit: int = 300) -> list[dict]:
        self.ensure_schema()
        rows = (
            db.session.query(WebsiteEStampOrder)
            .filter(WebsiteEStampOrder.IsPaid == True)  # noqa: E712
            .order_by(WebsiteEStampOrder.CreatedDate.desc())
            .limit(limit)
            .all()
        )
        return [self._row(row) for row in rows]

    def get_by_reference(self, reference_no: str) -> WebsiteEStampOrder | None:
        ref = _clean(reference_no, 40).upper()
        if not ref:
            return None
        return db.session.query(WebsiteEStampOrder).filter(WebsiteEStampOrder.ReferenceNo == ref).one_or_none()

    def create_paid(self, data: dict) -> dict:
        self.ensure_schema()
        first = _clean(data.get("name") or data.get("full_name") or data.get("first_party_name"))
        second = _clean(data.get("second_party_name"))
        mobile = _mobile(data.get("mobile") or "")
        article_code = _clean(data.get("article_code"), 40).lower()
        if len(first) < 2:
            raise ValueError("Please enter first party name.")
        if len(second) < 2:
            raise ValueError("Please enter second party name.")
        if len(mobile) != 10 or mobile[0] not in "6789":
            raise ValueError("Please enter a valid 10-digit mobile number.")
        article = article_by_code(article_code)
        if article is None:
            raise ValueError("Please select a stamp article.")
        try:
            amount = float(data.get("amount") or data.get("stamp_amount") or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("Please enter the stamp duty amount.") from exc
        if amount <= 0:
            raise ValueError("Please enter the stamp duty amount.")
        poi_type = _clean(data.get("poi_document_type"), 40).lower()
        if not poi_type:
            raise ValueError("Please select a proof of identity document type.")

        paid_flag = str(data.get("payment_status") or "").lower() in {"paid", "upi_paid"} or bool(data.get("paid"))
        if not paid_flag:
            raise ValueError("Order is recorded only after payment.")

        reference = _clean(data.get("reference_no"), 40).upper() or self._new_reference()
        existing = self.get_by_reference(reference)
        if existing:
            if not existing.IsPaid:
                existing.IsPaid = True
                existing.PaymentStatus = "paid"
            self._apply(existing, data, first, second, mobile, article, amount)
            existing.ModifiedDate = datetime.utcnow()
            db.session.commit()
            self._notify(existing)
            return self._public(existing, "Payment received. Reference Number: " + existing.ReferenceNo)

        customer_id = None
        try:
            customer = MasterRepository().find_or_create_customer(first, mobile)
            customer_id = customer.CustomerID
        except Exception:
            db.session.rollback()
            logger.warning("e-Stamp customer link skipped", exc_info=True)

        row = WebsiteEStampOrder(ReferenceNo=reference, CustomerID=customer_id)
        self._apply(row, data, first, second, mobile, article, amount)
        row.IsPaid = True
        row.PaymentStatus = "paid"
        row.ReviewStatus = "New"
        row.CreatedDate = datetime.utcnow()
        db.session.add(row)
        db.session.commit()
        self._notify(row)
        return self._public(row, "Payment received. Reference Number: " + row.ReferenceNo)

    def delete(self, reference_no: str, mobile: str) -> None:
        row = self.get_by_reference(reference_no)
        if row is None:
            return
        if _mobile(mobile) and _mobile(mobile) != _mobile(row.Mobile):
            raise ValueError("Mobile number does not match this request.")
        db.session.delete(row)
        db.session.commit()

    def save_poi(self, reference_no: str, file_storage, poi_type: str = "") -> dict:
        self.ensure_schema()
        row = self.get_by_reference(reference_no)
        if row is None:
            raise ValueError("e-Stamp order not found.")
        from pathlib import Path

        from app.services.dsc_documents import _save_upload

        folder = Path(current_app.config["UPLOAD_FOLDER"]) / "estamp_poi"
        path, name = _save_upload(folder, f"{row.ReferenceNo}_poi", file_storage)
        ext = Path(name).suffix.lower()
        if ext not in {".pdf", ".jpg", ".jpeg", ".png"}:
            raise ValueError("POI must be a PDF or image (JPG / PNG).")
        row.PoiDocPath = path
        row.PoiDocName = name
        if poi_type:
            row.PoiDocumentType = _clean(poi_type, 40).lower() or row.PoiDocumentType
        row.ModifiedDate = datetime.utcnow()
        db.session.commit()
        return self._public(row, "POI uploaded.")

    def poi_file(self, reference_no: str):
        row = self.get_by_reference(reference_no)
        if row is None or not row.PoiDocPath:
            raise ValueError("POI file not found.")
        from app.services.dsc_documents import _resolve_stored_path

        path = _resolve_stored_path(row.PoiDocPath)
        if not path.exists():
            raise ValueError("POI file is missing.")
        return path, row.PoiDocName or path.name

    NO_PAYMENT_WHATSAPP = (
        "Your stamp request has been rejected because you did not make the payment."
    )
    REJECT_WHATSAPP = (
        "Your stamp request has been rejected. Please contact JTCS for more information."
    )

    def update_review(self, reference_no: str, status: str, notes: str = "") -> dict:
        row = self.get_by_reference(reference_no)
        if row is None:
            raise ValueError("e-Stamp order not found.")
        row.ReviewStatus = _clean(status, 40) or row.ReviewStatus
        row.ReviewNotes = _clean(notes, 500) or None
        row.ModifiedDate = datetime.utcnow()
        db.session.commit()
        return self._row(row)

    def set_payment_confirm(self, reference_no: str, confirmed: str) -> dict:
        row = self.get_by_reference(reference_no)
        if row is None:
            raise ValueError("e-Stamp order not found.")
        choice = _clean(confirmed, 10).title()
        if choice not in {"Yes", "No"}:
            raise ValueError("Select Yes or No for payment confirm.")
        row.PaymentConfirmed = choice
        row.ModifiedDate = datetime.utcnow()
        if choice == "Yes":
            row.ReviewStatus = "Payment confirmed"
            db.session.commit()
            return self._row(row)
        return self.reject_order(reference_no, reason="no_payment")

    def reject_order(self, reference_no: str, reason: str = "rejected") -> dict:
        row = self.get_by_reference(reference_no)
        if row is None:
            raise ValueError("e-Stamp order not found.")
        no_pay = (reason or "").strip().lower() in {"no_payment", "no", "unpaid"}
        row.PaymentConfirmed = "No" if no_pay else (row.PaymentConfirmed or "Yes")
        row.ReviewStatus = "Rejected — no payment" if no_pay else "Rejected"
        row.ModifiedDate = datetime.utcnow()
        db.session.commit()
        message = self.NO_PAYMENT_WHATSAPP if no_pay else self.REJECT_WHATSAPP
        wa = self._whatsapp_applicant(row.Mobile, message)
        data = self._row(row)
        data["whatsapp"] = wa
        data["ok"] = True
        data["message"] = "Order rejected. WhatsApp reply prepared for the applicant."
        return data

    def admin_delete(self, reference_no: str) -> None:
        row = self.get_by_reference(reference_no)
        if row is None:
            return
        db.session.delete(row)
        db.session.commit()

    def admin_update(self, reference_no: str, data: dict) -> dict:
        row = self.get_by_reference(reference_no)
        if row is None:
            raise ValueError("e-Stamp order not found.")
        first = _clean(data.get("full_name") or data.get("name") or row.FullName)
        second = _clean(data.get("second_party_name") or row.SecondPartyName)
        if len(first) < 2:
            raise ValueError("Please enter first party name.")
        if len(second) < 2:
            raise ValueError("Please enter second party name.")
        row.FullName = first
        row.FatherOrHusbandName = _clean(data.get("father_or_husband_name")) or None
        row.SecondPartyName = second
        row.SecondPartyFatherOrHusbandName = _clean(data.get("second_party_father_or_husband_name")) or None
        desc = _clean(data.get("description"), 50)
        row.Description = desc or None
        consideration_raw = data.get("consideration_price")
        if consideration_raw in (None, ""):
            row.ConsiderationPrice = None
        else:
            try:
                row.ConsiderationPrice = float(consideration_raw)
            except (TypeError, ValueError) as exc:
                raise ValueError("Please enter a valid consideration price.") from exc
        try:
            amount = float(data.get("amount") if data.get("amount") not in (None, "") else row.Amount)
        except (TypeError, ValueError) as exc:
            raise ValueError("Please enter a valid stamp amount.") from exc
        if amount <= 0:
            raise ValueError("Please enter a valid stamp amount.")
        row.Amount = amount
        row.ModifiedDate = datetime.utcnow()
        db.session.commit()
        return self._row(row)

    def generate_stamp(self, reference_no: str) -> dict:
        row = self.get_by_reference(reference_no)
        if row is None:
            raise ValueError("e-Stamp order not found.")
        if (row.PaymentConfirmed or "") != "Yes":
            raise ValueError("Confirm payment as Yes before generating the stamp.")
        row.ReviewStatus = "Generate stamp"
        row.ModifiedDate = datetime.utcnow()
        db.session.commit()
        from flask import url_for

        stamp_url = url_for(
            "stamp.stamp_activity",
            mobile=row.Mobile or "",
            first_party=row.FullName or "",
            second_party=row.SecondPartyName or "",
            amount=str(row.Amount or ""),
            sale_amount=str(row.ConsiderationPrice or ""),
            description=row.Description or "",
            website_ref=row.ReferenceNo,
        )
        data = self._row(row)
        data["ok"] = True
        data["stamp_url"] = stamp_url
        data["message"] = "Opening Stamp Activity to generate the stamp."
        return data

    def _whatsapp_applicant(self, mobile: str, message: str) -> dict:
        digits = _mobile(mobile)
        result = {"ok": False, "wa_url": "", "sent": False}
        if not digits:
            result["error"] = "Applicant mobile is missing."
            return result
        try:
            from app.modules.communication.whatsapp_provider import get_whatsapp_provider

            provider = get_whatsapp_provider()
            sent = provider.send_message(digits, message) or {}
            result["sent"] = bool(sent.get("ok"))
            result["ok"] = bool(sent.get("ok") or sent.get("wa_url"))
            result["wa_url"] = sent.get("wa_url") or ""
            if not result["wa_url"] and hasattr(provider, "open_chat_url"):
                result["wa_url"] = provider.open_chat_url(digits, message) or ""
            if sent.get("error"):
                result["error"] = sent.get("error")
        except Exception as exc:
            logger.exception("e-Stamp applicant WhatsApp failed")
            result["error"] = str(exc)
        if not result["wa_url"]:
            from urllib.parse import quote

            result["wa_url"] = "https://wa.me/91" + digits + "?text=" + quote(message)
            result["ok"] = True
        return result

    def _apply(self, row: WebsiteEStampOrder, data: dict, first: str, second: str, mobile: str, article: dict, amount: float) -> None:
        row.FullName = first
        row.FatherOrHusbandName = _clean(data.get("father_or_husband_name") or data.get("father_name")) or None
        row.SecondPartyName = second
        row.SecondPartyFatherOrHusbandName = _clean(data.get("second_party_father_or_husband_name")) or None
        row.Mobile = mobile
        row.ArticleCode = article["code"]
        row.ArticleLabel = article_display(article)
        row.Amount = amount
        try:
            row.PayableAmount = float(data.get("payable_amount") or amount)
        except (TypeError, ValueError):
            row.PayableAmount = amount
        row.DeliveryMode = _clean(data.get("delivery_mode"), 20) or "self"
        row.HouseNo = _clean(data.get("house_no"), 80) or None
        row.Gali = _clean(data.get("gali")) or None
        row.Mohalla = _clean(data.get("mohalla")) or None
        row.Landmark = _clean(data.get("landmark"), 200) or None
        row.AddressNote = _clean(data.get("address_note"), 300) or None
        row.GeoAddress = _clean(data.get("geo_address"), 400) or None
        row.LocationUrl = _clean(data.get("location_url"), 500) or None
        row.PayMethod = _clean(data.get("pay_method"), 40) or "upi"
        row.UtrNumber = _clean(data.get("utr_number") or data.get("utr"), 40) or None
        description = _clean(data.get("description"), 50)
        row.Description = description or None
        row.PoiDocumentType = _clean(data.get("poi_document_type"), 40).lower() or None
        consideration_raw = data.get("consideration_price")
        if consideration_raw in (None, ""):
            row.ConsiderationPrice = None
        else:
            try:
                row.ConsiderationPrice = float(consideration_raw)
            except (TypeError, ValueError):
                row.ConsiderationPrice = None

    def _new_reference(self) -> str:
        day = datetime.utcnow().strftime("%Y%m%d")
        return f"EST-{day}-{secrets.token_hex(2).upper()}"

    def _row(self, row: WebsiteEStampOrder) -> dict:
        return {
            "order_id": row.OrderID,
            "reference_no": row.ReferenceNo,
            "full_name": row.FullName,
            "father_or_husband_name": row.FatherOrHusbandName or "",
            "second_party_name": row.SecondPartyName or "",
            "second_party_father_or_husband_name": row.SecondPartyFatherOrHusbandName or "",
            "mobile": row.Mobile,
            "consideration_price": float(row.ConsiderationPrice) if row.ConsiderationPrice is not None else "",
            "description": row.Description or "",
            "poi_document_type": POI_LABELS.get((row.PoiDocumentType or "").lower(), row.PoiDocumentType or ""),
            "poi_file_name": row.PoiDocName or "",
            "poi_has_file": bool(row.PoiDocPath),
            "article_code": row.ArticleCode,
            "article_label": row.ArticleLabel,
            "amount": float(row.Amount or 0),
            "payable_amount": float(row.PayableAmount or row.Amount or 0),
            "delivery_mode": row.DeliveryMode,
            "pay_method": row.PayMethod,
            "utr_number": row.UtrNumber or "",
            "payment_status": row.PaymentStatus,
            "review_status": row.ReviewStatus,
            "review_notes": row.ReviewNotes or "",
            "payment_confirmed": (row.PaymentConfirmed or "").strip(),
            "created_date": row.CreatedDate.strftime("%d/%m/%Y %H:%M") if row.CreatedDate else "",
        }

    def _public(self, row: WebsiteEStampOrder, message: str) -> dict:
        data = self._row(row)
        data["ok"] = True
        data["message"] = message
        return data

    def _notify(self, row: WebsiteEStampOrder) -> None:
        title = f"e-Stamp paid {row.ReferenceNo}"
        body = (
            f"Reference: {row.ReferenceNo}\n"
            f"First party: {row.FullName}\n"
            f"Second party: {row.SecondPartyName}\n"
            f"Mobile: {row.Mobile}\n"
            f"POI: {row.PoiDocumentType or '-'} ({row.PoiDocName or 'not uploaded'})\n"
            f"Consideration: {row.ConsiderationPrice if row.ConsiderationPrice is not None else '-'}\n"
            f"Description: {row.Description or '-'}\n"
            f"Article: {row.ArticleLabel}\n"
            f"Stamp: ₹{row.Amount}\n"
            f"Payable: ₹{row.PayableAmount or row.Amount}\n"
            f"Pay method: {row.PayMethod or 'UPI'}\n"
            f"UTR: {row.UtrNumber or '-'}"
        )
        try:
            from app.modules.notification.services import NotificationService

            NotificationService().notify_roles_or_all(
                notification_type="Payment",
                title=title,
                message=body.replace("\n", " · "),
                link_url="/admin/estamp-orders",
                priority="High",
                entity_type="WebsiteEStampOrder",
                entity_id=row.OrderID,
            )
        except Exception:
            logger.exception("e-Stamp in-app notification failed")

        company = db.session.query(CompanyProfile).first()
        email_to = (company.Email if company else None) or current_app.config.get("MAIL_DEFAULT_SENDER")
        if email_to:
            try:
                sender = current_app.config.get("MAIL_DEFAULT_SENDER") or current_app.config.get("MAIL_USERNAME")
                mail.send(
                    Message(
                        subject=title,
                        recipients=[str(email_to)],
                        body=body,
                        sender=sender,
                    )
                )
            except Exception:
                logger.exception("e-Stamp email notification failed")

        mobile = (company.MobileNumber if company else "") or ""
        if mobile:
            try:
                from app.modules.communication.whatsapp_provider import get_whatsapp_provider

                get_whatsapp_provider().send_message(mobile, title + "\n" + body)
            except Exception:
                logger.exception("e-Stamp WhatsApp notification failed")


OFFICE_LAT = 29.24016638055615
OFFICE_LNG = 79.53455680423431


def _http_json(url: str, timeout: int = 12) -> dict:
    import json
    from urllib.request import Request, urlopen

    req = Request(url, headers={"Accept": "application/json", "User-Agent": "JTCS-eStamp/1.0"})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _google_maps_key() -> str:
    try:
        from app.modules.settings.services import IntegrationSettingsService

        cfg = IntegrationSettingsService().get_provider_config_decrypted("google") or {}
        return str(cfg.get("api_key") or "").strip()
    except Exception:
        return ""


def driving_route_km(lat: float, lng: float) -> tuple[float, str]:
    """Google driving route first; OSRM road route fallback. Returns (km, source)."""
    key = _google_maps_key()
    if key:
        from urllib.parse import urlencode

        qs = urlencode(
            {
                "origin": f"{OFFICE_LAT},{OFFICE_LNG}",
                "destination": f"{lat},{lng}",
                "mode": "driving",
                "key": key,
            }
        )
        try:
            data = _http_json("https://maps.googleapis.com/maps/api/directions/json?" + qs)
            routes = data.get("routes") or []
            legs = (routes[0].get("legs") if routes else None) or []
            meters = ((legs[0] or {}).get("distance") or {}).get("value")
            if meters and float(meters) > 0:
                return round(float(meters) / 1000.0, 2), "google"
        except Exception:
            logger.exception("Google driving distance failed")

    osrm = (
        f"https://router.project-osrm.org/route/v1/driving/"
        f"{OFFICE_LNG},{OFFICE_LAT};{lng},{lat}?overview=false&alternatives=false"
    )
    data = _http_json(osrm)
    routes = data.get("routes") or []
    meters = (routes[0] or {}).get("distance") if routes else None
    if not meters or float(meters) <= 0:
        raise ValueError("Unable to calculate road distance.")
    return round(float(meters) / 1000.0, 2), "osrm"
