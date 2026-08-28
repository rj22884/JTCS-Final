"""Read JTCS Property website SQLite from ERP Admin Role (same pattern as recruitment).

Property registrations stay in the website property module database.
This service does not copy Aadhaar files or unmask public APIs.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from flask import current_app


class PropertyStoreError(RuntimeError):
    pass


def _db_path() -> Path:
    return Path(current_app.config["PROPERTY_DB_PATH"])


def store_available() -> tuple[bool, str]:
    path = _db_path()
    if not path.is_file():
        return False, f"Property database not found at {path}"
    return True, str(path)


def _connect() -> sqlite3.Connection:
    path = _db_path()
    if not path.is_file():
        raise PropertyStoreError(
            "Property registrations are stored with the website Property module. "
            f"Database not found: {path}"
        )
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _row(row: sqlite3.Row | None) -> dict:
    return dict(row) if row is not None else {}


def summary() -> dict:
    with _connect() as con:
        def _n(sql: str, params: tuple = ()) -> int:
            return int(con.execute(sql, params).fetchone()[0] or 0)

        return {
            "listings": _n("SELECT COUNT(*) FROM property_listings"),
            "pending": _n("SELECT COUNT(*) FROM property_listings WHERE status = ?", ("Pending Verification",)),
            "verified": _n("SELECT COUNT(*) FROM property_listings WHERE is_verified = 1"),
            "rejected": _n("SELECT COUNT(*) FROM property_listings WHERE status = ?", ("Rejected",)),
            "published": _n("SELECT COUNT(*) FROM property_listings WHERE status = ?", ("Published",)),
            "owners": _n("SELECT COUNT(*) FROM property_owners"),
            "buyers": _n("SELECT COUNT(*) FROM property_seekers"),
            "leads": _n("SELECT COUNT(*) FROM property_leads"),
            "site_visits": _n("SELECT COUNT(*) FROM property_leads WHERE lead_type = ?", ("site_visit",)),
            "requirements": _n("SELECT COUNT(*) FROM property_requirements"),
            "deals": _n("SELECT COUNT(*) FROM property_brokerage_deals"),
        }


def list_listings(search: str = "", status: str = "") -> list[dict]:
    q = (search or "").strip()
    status = (status or "").strip()
    sql = """
        SELECT
            l.property_id,
            l.public_id,
            l.listing_number,
            l.title,
            l.listing_type,
            l.property_type,
            l.status,
            l.is_verified,
            l.locality,
            l.price,
            l.updated_at,
            o.full_name AS owner_name,
            o.mobile AS owner_mobile
        FROM property_listings l
        LEFT JOIN property_owners o ON o.owner_id = l.owner_id
        WHERE 1 = 1
    """
    params: list = []
    if status:
        sql += " AND l.status = ?"
        params.append(status)
    if q:
        like = f"%{q}%"
        sql += """
            AND (
                l.listing_number LIKE ?
                OR l.title LIKE ?
                OR l.locality LIKE ?
                OR o.full_name LIKE ?
                OR o.mobile LIKE ?
            )
        """
        params.extend([like, like, like, like, like])
    sql += " ORDER BY l.updated_at DESC"
    with _connect() as con:
        return [_row(r) for r in con.execute(sql, params)]


def get_listing(public_id: str) -> dict | None:
    with _connect() as con:
        listing = _row(
            con.execute(
                """
                SELECT
                    l.property_id, l.public_id, l.listing_number, l.title, l.description,
                    l.listing_type, l.property_type, l.status, l.is_verified,
                    l.locality, l.address, l.city, l.price, l.bhk, l.furnishing,
                    l.ownership_status, l.declaration_accepted, l.updated_at,
                    o.full_name AS owner_name, o.mobile AS owner_mobile, o.email AS owner_email
                FROM property_listings l
                LEFT JOIN property_owners o ON o.owner_id = l.owner_id
                WHERE l.public_id = ?
                """,
                (public_id,),
            ).fetchone()
        )
        if not listing:
            return None
        listing["photos"] = [
            _row(r)
            for r in con.execute(
                "SELECT photo_id, original_name FROM property_photos WHERE property_id = ? ORDER BY photo_id",
                (listing["property_id"],),
            )
        ]
        listing["documents"] = [
            _row(r)
            for r in con.execute(
                """
                SELECT document_id, doc_type, original_name, aadhaar_last4
                FROM property_documents
                WHERE property_id = ?
                ORDER BY document_id
                """,
                (listing["property_id"],),
            )
        ]
        listing["leads"] = [
            _row(r)
            for r in con.execute(
                """
                SELECT lead_id, name, mobile, lead_type, status, preferred_date, preferred_time
                FROM property_leads
                WHERE property_id = ?
                ORDER BY lead_id DESC
                """,
                (listing["property_id"],),
            )
        ]
        listing["deals"] = [
            _row(r)
            for r in con.execute(
                """
                SELECT deal_id, deal_number, status, total_amount, payment_status
                FROM property_brokerage_deals
                WHERE property_id = ?
                ORDER BY deal_id DESC
                """,
                (listing["property_id"],),
            )
        ]
        return listing


def list_owners() -> list[dict]:
    with _connect() as con:
        return [
            _row(r)
            for r in con.execute(
                """
                SELECT owner_id, full_name, mobile, email, created_at,
                       (SELECT COUNT(*) FROM property_listings l WHERE l.owner_id = o.owner_id) AS listings
                FROM property_owners o
                ORDER BY owner_id DESC
                LIMIT 300
                """
            )
        ]


def list_buyers() -> list[dict]:
    with _connect() as con:
        return [
            _row(r)
            for r in con.execute(
                "SELECT seeker_id, full_name, mobile, email, created_at FROM property_seekers ORDER BY seeker_id DESC LIMIT 300"
            )
        ]


def list_leads(lead_type: str = "") -> list[dict]:
    sql = """
        SELECT lead.lead_id, lead.name, lead.mobile, lead.lead_type, lead.status,
               lead.preferred_date, l.listing_number
        FROM property_leads lead
        LEFT JOIN property_listings l ON l.property_id = lead.property_id
        WHERE 1 = 1
    """
    params: list = []
    if lead_type:
        sql += " AND lead.lead_type = ?"
        params.append(lead_type)
    sql += " ORDER BY lead.lead_id DESC LIMIT 300"
    with _connect() as con:
        return [_row(r) for r in con.execute(sql, params)]


def list_requirements() -> list[dict]:
    with _connect() as con:
        return [
            _row(r)
            for r in con.execute(
                """
                SELECT r.requirement_id, r.requirement_number, r.requirement_type, r.property_type,
                       r.locality, r.max_budget, r.status, s.full_name, s.mobile
                FROM property_requirements r
                LEFT JOIN property_seekers s ON s.seeker_id = r.seeker_id
                ORDER BY r.requirement_id DESC
                LIMIT 300
                """
            )
        ]


def list_deals() -> list[dict]:
    with _connect() as con:
        return [
            _row(r)
            for r in con.execute(
                """
                SELECT d.deal_id, d.deal_number, d.status, d.total_amount, d.payment_status,
                       d.owner_amount, d.buyer_amount, l.listing_number
                FROM property_brokerage_deals d
                LEFT JOIN property_listings l ON l.property_id = d.property_id
                ORDER BY d.deal_id DESC
                LIMIT 300
                """
            )
        ]


def list_agreements() -> list[dict]:
    with _connect() as con:
        return [
            _row(r)
            for r in con.execute(
                """
                SELECT a.agreement_id, a.agreement_type, a.status, d.deal_number, l.listing_number
                FROM property_deal_agreements a
                LEFT JOIN property_brokerage_deals d ON d.deal_id = a.deal_id
                LEFT JOIN property_listings l ON l.property_id = d.property_id
                ORDER BY a.agreement_id DESC
                LIMIT 300
                """
            )
        ]
