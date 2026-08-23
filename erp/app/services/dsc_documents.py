"""DSC document storage on Customer Master + website applications."""

from __future__ import annotations

import io
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from flask import current_app
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from sqlalchemy import text

from app.extensions import db
from app.repositories.customer_repository import CustomerRepository

logger = logging.getLogger(__name__)

GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]Z[A-Z0-9]$")
ALLOWED_EXT = {".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx"}
MAX_BYTES = 8 * 1024 * 1024

DSC_DOC_KINDS = {
    "pan": {
        "label": "PAN",
        "path_col": "DscPanDocPath",
        "name_col": "DscPanDocName",
        "app_path": "PanDocPath",
        "app_name": "PanDocName",
    },
    "aadhaar": {
        "label": "Aadhaar",
        "path_col": "DscAadhaarDocPath",
        "name_col": "DscAadhaarDocName",
        "app_path": "AadhaarDocPath",
        "app_name": "AadhaarDocName",
    },
    "org_id": {
        "label": "Organization ID",
        "path_col": "DscOrgIdDocPath",
        "name_col": "DscOrgIdDocName",
        "app_path": "OrgIdDocPath",
        "app_name": "OrgIdDocName",
    },
    "auth_letter": {
        "label": "Authorization Letter",
        "path_col": "DscAuthLetterPath",
        "name_col": "DscAuthLetterName",
        "app_path": "AuthLetterPath",
        "app_name": "AuthLetterName",
    },
}

_SCHEMA_STMTS = (
    "IF COL_LENGTH(N'dbo.CustomerMaster', N'DscPanDocPath') IS NULL ALTER TABLE dbo.CustomerMaster ADD DscPanDocPath NVARCHAR(400) NULL",
    "IF COL_LENGTH(N'dbo.CustomerMaster', N'DscPanDocName') IS NULL ALTER TABLE dbo.CustomerMaster ADD DscPanDocName NVARCHAR(180) NULL",
    "IF COL_LENGTH(N'dbo.CustomerMaster', N'DscAadhaarDocPath') IS NULL ALTER TABLE dbo.CustomerMaster ADD DscAadhaarDocPath NVARCHAR(400) NULL",
    "IF COL_LENGTH(N'dbo.CustomerMaster', N'DscAadhaarDocName') IS NULL ALTER TABLE dbo.CustomerMaster ADD DscAadhaarDocName NVARCHAR(180) NULL",
    "IF COL_LENGTH(N'dbo.CustomerMaster', N'DscOrgIdDocPath') IS NULL ALTER TABLE dbo.CustomerMaster ADD DscOrgIdDocPath NVARCHAR(400) NULL",
    "IF COL_LENGTH(N'dbo.CustomerMaster', N'DscOrgIdDocName') IS NULL ALTER TABLE dbo.CustomerMaster ADD DscOrgIdDocName NVARCHAR(180) NULL",
    "IF COL_LENGTH(N'dbo.CustomerMaster', N'DscAuthLetterPath') IS NULL ALTER TABLE dbo.CustomerMaster ADD DscAuthLetterPath NVARCHAR(400) NULL",
    "IF COL_LENGTH(N'dbo.CustomerMaster', N'DscAuthLetterName') IS NULL ALTER TABLE dbo.CustomerMaster ADD DscAuthLetterName NVARCHAR(180) NULL",
    "IF COL_LENGTH(N'dbo.WebsiteDscApplication', N'OrganizationAddress') IS NULL ALTER TABLE dbo.WebsiteDscApplication ADD OrganizationAddress NVARCHAR(400) NULL",
    "IF COL_LENGTH(N'dbo.WebsiteDscApplication', N'PanDocPath') IS NULL ALTER TABLE dbo.WebsiteDscApplication ADD PanDocPath NVARCHAR(400) NULL",
    "IF COL_LENGTH(N'dbo.WebsiteDscApplication', N'PanDocName') IS NULL ALTER TABLE dbo.WebsiteDscApplication ADD PanDocName NVARCHAR(180) NULL",
    "IF COL_LENGTH(N'dbo.WebsiteDscApplication', N'AadhaarDocPath') IS NULL ALTER TABLE dbo.WebsiteDscApplication ADD AadhaarDocPath NVARCHAR(400) NULL",
    "IF COL_LENGTH(N'dbo.WebsiteDscApplication', N'AadhaarDocName') IS NULL ALTER TABLE dbo.WebsiteDscApplication ADD AadhaarDocName NVARCHAR(180) NULL",
    "IF COL_LENGTH(N'dbo.WebsiteDscApplication', N'OrgIdDocPath') IS NULL ALTER TABLE dbo.WebsiteDscApplication ADD OrgIdDocPath NVARCHAR(400) NULL",
    "IF COL_LENGTH(N'dbo.WebsiteDscApplication', N'OrgIdDocName') IS NULL ALTER TABLE dbo.WebsiteDscApplication ADD OrgIdDocName NVARCHAR(180) NULL",
)


def ensure_dsc_doc_schema() -> None:
    for sql in _SCHEMA_STMTS:
        db.session.execute(text(sql))
    db.session.commit()


def normalize_gstin(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()


def attach_customer_doc_flags(data: dict, row: dict) -> dict:
    docs = []
    for kind, meta in DSC_DOC_KINDS.items():
        path = (row.get(meta["path_col"]) or "").strip()
        name = (row.get(meta["name_col"]) or "").strip()
        item = {
            "kind": kind,
            "label": meta["label"],
            "file_name": name,
            "has_file": bool(path),
        }
        docs.append(item)
        data[f"dsc_{kind}_has_file"] = bool(path)
        data[f"dsc_{kind}_file_name"] = name
    data["dsc_docs"] = docs
    return data


def customer_doc_status(customer_id: int) -> list[dict]:
    ensure_dsc_doc_schema()
    row = db.session.execute(
        text("SELECT * FROM dbo.CustomerMaster WHERE CustomerID = :id"),
        {"id": int(customer_id)},
    ).mappings().first()
    if not row:
        return []
    data: dict = {}
    attach_customer_doc_flags(data, dict(row))
    return data["dsc_docs"]


def _safe_name(filename: str) -> str:
    name = Path(filename or "document").name
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name)[:160]


def _save_upload(folder: Path, stem: str, file_storage) -> tuple[str, str]:
    if not file_storage or not file_storage.filename:
        raise ValueError("Please choose a file to upload.")
    name = _safe_name(file_storage.filename)
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise ValueError("Upload PDF, JPG, PNG or Word file only.")
    file_storage.stream.seek(0, 2)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size > MAX_BYTES:
        raise ValueError("File must be 8 MB or smaller.")
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"{stem}_{name}"
    file_storage.save(dest)
    try:
        rel = dest.relative_to(Path(current_app.config["UPLOAD_FOLDER"]))
        store_path = f"uploads/{rel.as_posix()}"
    except ValueError:
        store_path = str(dest)
    return store_path, name


def save_customer_doc(customer_id: int, kind: str, file_storage, *, actor: str = "") -> dict:
    meta = DSC_DOC_KINDS.get((kind or "").strip().lower())
    if not meta:
        raise ValueError("Unknown DSC document type.")
    ensure_dsc_doc_schema()
    row = db.session.execute(
        text("SELECT CustomerID FROM dbo.CustomerMaster WHERE CustomerID = :id"),
        {"id": int(customer_id)},
    ).first()
    if not row:
        raise ValueError("Customer not found.")
    folder = Path(current_app.config["UPLOAD_FOLDER"]) / "customer_dsc" / str(int(customer_id))
    path, name = _save_upload(folder, meta["path_col"], file_storage)
    db.session.execute(
        text(
            f"UPDATE dbo.CustomerMaster SET {meta['path_col']} = :path, {meta['name_col']} = :name, "
            "ModifiedDate = SYSUTCDATETIME() WHERE CustomerID = :id"
        ),
        {"path": path, "name": name, "id": int(customer_id)},
    )
    db.session.commit()
    _mirror_crm_document(int(customer_id), meta["label"], name, path, actor)
    return {"ok": True, "kind": kind, "file_name": name, "has_file": True}


def customer_doc_file(customer_id: int, kind: str) -> tuple[Path, str]:
    meta = DSC_DOC_KINDS.get((kind or "").strip().lower())
    if not meta:
        raise ValueError("Unknown DSC document type.")
    ensure_dsc_doc_schema()
    row = db.session.execute(
        text(
            f"SELECT {meta['path_col']} AS DocPath, {meta['name_col']} AS DocName "
            "FROM dbo.CustomerMaster WHERE CustomerID = :id"
        ),
        {"id": int(customer_id)},
    ).mappings().first()
    if not row or not row.get("DocPath"):
        raise ValueError("Document is not uploaded yet.")
    path = _resolve_stored_path(row["DocPath"])
    if not path.exists():
        raise ValueError("Document file is missing.")
    return path, row.get("DocName") or path.name


def _resolve_stored_path(stored: str) -> Path:
    raw = str(stored or "").replace("\\", "/")
    if raw.startswith("uploads/"):
        return Path(current_app.config["UPLOAD_FOLDER"]) / raw[len("uploads/") :]
    path = Path(raw)
    if path.is_absolute():
        return path
    return Path(current_app.config["UPLOAD_FOLDER"]) / raw


def _mirror_crm_document(customer_id: int, title: str, file_name: str, stored_path: str, actor: str) -> None:
    try:
        exists = db.session.execute(
            text("SELECT OBJECT_ID(N'dbo.CrmDocument', N'U') AS oid")
        ).scalar()
        if not exists:
            return
        db.session.execute(
            text(
                """
                INSERT INTO dbo.CrmDocument (
                    CustomerID, FolderType, Title, FileName, StoredPath, MimeType,
                    UploadedByName, Source, IsActive, CreatedDate
                )
                VALUES (
                    :cid, N'DSC', :title, :fname, :spath, NULL,
                    :actor, N'DSC', 1, SYSUTCDATETIME()
                )
                """
            ),
            {
                "cid": customer_id,
                "title": f"DSC — {title}",
                "fname": file_name,
                "spath": stored_path,
                "actor": (actor or "DSC")[:150],
            },
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.warning("CRM document mirror skipped", exc_info=True)


def pan_exists(pan: str) -> bool:
    repo = CustomerRepository()
    found = repo.find_by_pan(pan)
    return bool(found)


def search_gstin(gstin: str) -> dict:
    code = normalize_gstin(gstin)
    if not GSTIN_RE.match(code):
        raise ValueError("Enter a valid 15-character GSTIN.")
    local = _gstin_from_customer(code)
    if local:
        return local
    public = _gstin_from_public(code)
    if public:
        return public
    return {
        "ok": True,
        "found": False,
        "gstin": code,
        "legal_name": "",
        "trade_name": "",
        "address": "",
        "message": "GSTIN not found. Enter organization name and address.",
    }


def _gstin_from_customer(gstin: str) -> dict | None:
    row = db.session.execute(
        text(
            """
            SELECT TOP 1 CustomerName, CompanyFirmName, GSTNumber,
                   AddressLine1, AddressLine2, Area, City, District, State, Pincode
            FROM dbo.CustomerMaster
            WHERE REPLACE(UPPER(ISNULL(GSTNumber, N'')), N' ', N'') = :gstin
              AND CustomerStatus <> N'Inactive'
            """
        ),
        {"gstin": gstin},
    ).mappings().first()
    if not row:
        return None
    parts = [
        row.get("AddressLine1"),
        row.get("AddressLine2"),
        row.get("Area"),
        row.get("City"),
        row.get("District"),
        row.get("State"),
        row.get("Pincode"),
    ]
    address = ", ".join(str(p).strip() for p in parts if p and str(p).strip())
    name = (row.get("CompanyFirmName") or row.get("CustomerName") or "").strip()
    return {
        "ok": True,
        "found": True,
        "source": "customer_master",
        "gstin": gstin,
        "legal_name": name,
        "trade_name": (row.get("CustomerName") or "").strip(),
        "address": address,
        "message": "Organization found from Customer Master.",
    }


def _gstin_from_public(gstin: str) -> dict | None:
    url = "https://blog-backend.mastersindia.co/api/v1/custom/search/gstin?keyword=" + gstin
    req = Request(url, headers={"User-Agent": "JTCS-ERP/1.0", "Accept": "application/json"})
    try:
        with urlopen(req, timeout=8) as resp:
            payload = json.loads(resp.read().decode("utf-8", "ignore") or "{}")
    except (URLError, TimeoutError, ValueError, OSError):
        return None
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return None
    legal = str(data.get("lgnm") or data.get("legal_name") or data.get("legalName") or "").strip()
    trade = str(data.get("tradeNam") or data.get("trade_name") or data.get("tradeName") or "").strip()
    address = _flatten_gst_address(data)
    if not legal and not address:
        return None
    return {
        "ok": True,
        "found": True,
        "source": "gst_search",
        "gstin": gstin,
        "legal_name": legal or trade,
        "trade_name": trade,
        "address": address,
        "message": "Organization found from GSTIN search.",
    }


def _flatten_gst_address(data: dict) -> str:
    pradr = data.get("pradr") if isinstance(data.get("pradr"), dict) else {}
    addr = pradr.get("addr") if isinstance(pradr.get("addr"), dict) else {}
    if not addr and isinstance(data.get("address"), str):
        return data.get("address") or ""
    parts = [
        addr.get("bno"),
        addr.get("flno"),
        addr.get("bnm"),
        addr.get("st"),
        addr.get("loc"),
        addr.get("dst"),
        addr.get("stcd"),
        addr.get("pncd"),
    ]
    return ", ".join(str(p).strip() for p in parts if p and str(p).strip())


def authorization_letter_pdf(fields: dict) -> bytes:
    def val(key: str) -> str:
        return " ".join(str(fields.get(key) or "").split())

    person = val("authorized_person_name") or "_________________"
    email = val("authorized_email") or "_________________"
    mobile = val("authorized_mobile") or "_________________"
    signatory = val("signatory_name") or "_________________"
    org = val("organization_name") or "_________________"
    designation = val("designation") or "_________________"
    sign_mobile = val("signatory_mobile") or "_________________"
    sign_email = val("signatory_email") or "_________________"

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="Proof of Sufficient Authorization by Organization",
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "DscTitle",
        parent=styles["Heading1"],
        fontSize=13,
        leading=16,
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    sub = ParagraphStyle(
        "DscSub",
        parent=styles["Normal"],
        fontSize=10,
        leading=13,
        alignment=TA_CENTER,
        spaceAfter=2,
    )
    body = ParagraphStyle(
        "DscBody",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        alignment=TA_JUSTIFY,
        spaceAfter=8,
    )
    left = ParagraphStyle("DscLeft", parent=body, alignment=TA_LEFT)
    story = [
        Paragraph("Proof of Sufficient Authorization by Organization", title),
        Paragraph("To be signed by Authorized Signatory – (Director / Partner)", sub),
        Paragraph("(To be printed on organization letter head / Office seal)", sub),
        Spacer(1, 10),
        Paragraph("To:", left),
        Paragraph("QCID Technologies Private Limited", left),
        Paragraph("Plot NO 1303 &amp; 1304, 1st Floor,", left),
        Paragraph("Khanamet, Ayyappa Society,", left),
        Paragraph("Madhapur, Hyderabad – 500081, Telangana", left),
        Spacer(1, 8),
        Paragraph("<b>Subject:</b> Confirmation of Authorization Letter for Digital Signature Certificate", left),
        Paragraph("This is to confirm that:", body),
        Paragraph(f"<b>Mr. / Ms.:</b> {person}", left),
        Paragraph(f"<b>Email ID:</b> {email}", left),
        Paragraph(f"<b>Mobile No:</b> {mobile}", left),
        Paragraph(
            "has been authorized to apply for DSC referred above and he/she has been authorized "
            "to use the said DSC on behalf of our organization.",
            body,
        ),
        Paragraph(
            "By this, he/she is authorized to act as an “Authorized Signatory” (as per the definition "
            "of Identity Verification Guidelines of CCA) towards further authorizing the enrolments of "
            "Organization employees for creation of their KYC account (to enroll for DSC/eSign). The "
            "acts done and documents shall be binding on the Organization. I am having suitable "
            "authority/authorization to provide this authorization on behalf of the Organization.",
            body,
        ),
        Paragraph("For the Organization (with Signature &amp; Seal)", left),
        Paragraph("<b>Authorized Signatory</b>", left),
        Paragraph(f"Name: {signatory}", left),
        Paragraph(f"ORG Name: {org}", left),
        Paragraph(f"Department &amp; Designation: {designation}", left),
        Paragraph(f"Mobile: {sign_mobile}", left),
        Paragraph(f"Email Id: {sign_email}", left),
        Spacer(1, 10),
        Paragraph(
            "* Please enclose the proof of Identity of the Auth person (PAN / DL / Passport / any Govt issued ID)",
            left,
        ),
        Paragraph(f"Generated: {datetime.now().strftime('%d/%m/%Y %H:%M')}", left),
    ]
    doc.build(story)
    return buffer.getvalue()
