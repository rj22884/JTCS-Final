"""Read Sales Executive applications from the website recruitment SQLite database.

HR status changes in ERP are written back to job_applications so the public
application-status page stays in sync.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app


class RecruitmentStoreError(RuntimeError):
    pass


def _db_path() -> Path:
    return Path(current_app.config["RECRUITMENT_DB_PATH"])


def _upload_dir() -> Path:
    return Path(current_app.config["RECRUITMENT_UPLOAD_DIR"])


def store_available() -> tuple[bool, str]:
    path = _db_path()
    if not path.is_file():
        return False, f"Recruitment database not found at {path}"
    return True, str(path)


def _connect() -> sqlite3.Connection:
    path = _db_path()
    if not path.is_file():
        raise RecruitmentStoreError(
            "Sales Executive applications are stored with the website recruitment module. "
            f"Database not found: {path}"
        )
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _connect_rw() -> sqlite3.Connection:
    path = _db_path()
    if not path.is_file():
        raise RecruitmentStoreError(
            "Sales Executive applications are stored with the website recruitment module. "
            f"Database not found: {path}"
        )
    con = sqlite3.connect(str(path), timeout=15)
    con.row_factory = sqlite3.Row
    return con


WEBSITE_STATUS_FROM_HR = {
    "Interview": "Interview Scheduled",
    "Offer": "Offer Issued",
    "Appointment": "Appointment Issued",
    "Employee": "Appointment Issued",
}


def website_status_for_store(status: str | None) -> str:
    raw = (status or "New").strip() or "New"
    return WEBSITE_STATUS_FROM_HR.get(raw, raw)


_STATUS_RANK = {
    "New": 0,
    "Under Review": 1,
    "Shortlisted": 2,
    "Interview": 3,
    "Interview Scheduled": 3,
    "Interviewed": 4,
    "Selected": 5,
    "Offer": 6,
    "Offer Issued": 6,
    "Offer Accepted": 7,
    "Appointment": 8,
    "Appointment Issued": 8,
    "Employee": 9,
}


def website_needs_status_sync(current: str | None, desired: str | None) -> bool:
    """True when the public SQLite row is behind the HR/pipeline status."""
    desired_store = website_status_for_store(desired)
    current_store = (current or "").strip()
    if not desired_store or desired_store == current_store:
        return False
    if desired_store in {"Rejected", "On Hold"}:
        return True
    return _STATUS_RANK.get(desired_store, 0) > _STATUS_RANK.get(current_store, 0)


def preferred_website_status(overlay: str | None, pipeline: str | None) -> str:
    overlay_store = website_status_for_store(overlay) if overlay else ""
    if overlay_store in {"Rejected", "On Hold"}:
        return overlay_store
    mapped = [website_status_for_store(s) for s in (overlay, pipeline) if s]
    if not mapped:
        return "New"
    return max(mapped, key=lambda s: _STATUS_RANK.get(s, 0))


def update_application_status(
    application_id: int,
    new_status: str,
    changed_by: str = "",
    reason: str = "",
) -> bool:
    """Update website job_applications so candidate status page matches HR."""
    new_status = website_status_for_store(new_status)
    with _connect_rw() as con:
        row = con.execute(
            "SELECT application_status FROM job_applications WHERE application_id = ?",
            (int(application_id),),
        ).fetchone()
        if row is None:
            return False
        old = (row["application_status"] or "").strip()
        if old == new_status:
            return False
        now = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")
        con.execute(
            """
            UPDATE job_applications
            SET application_status = ?, updated_at = ?
            WHERE application_id = ?
            """,
            (new_status, now, int(application_id)),
        )
        con.execute(
            """
            INSERT INTO application_status_history
                (application_id, old_status, new_status, changed_by, change_reason, changed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                int(application_id),
                old or None,
                new_status,
                (changed_by or "HR Admin")[:200],
                (reason or "Updated from HR")[:500],
                now,
            ),
        )
        con.commit()
    return True


def _row(row: sqlite3.Row | None) -> dict:
    return dict(row) if row is not None else {}


def list_applications(search: str = "", status: str = "") -> list[dict]:
    q = (search or "").strip()
    status = (status or "").strip()
    sql = """
        SELECT
            a.application_id,
            a.application_number,
            a.application_status,
            a.source,
            a.submitted_at,
            a.expected_salary,
            a.resume_stored_name,
            a.application_pdf_stored_name,
            a.interview_result,
            a.interview_mode,
            a.willing_to_work_haldwani,
            c.name,
            c.father_name,
            c.mobile,
            c.email,
            c.city,
            c.state,
            j.job_title,
            e.total_work_experience,
            e.sales_experience_years,
            e.sales_experience_months
        FROM job_applications a
        JOIN candidates c ON c.candidate_id = a.candidate_id
        JOIN jobs j ON j.job_id = a.job_id
        LEFT JOIN candidate_experience e ON e.candidate_id = c.candidate_id
        WHERE 1 = 1
    """
    params: list = []
    if status:
        sql += " AND a.application_status = ?"
        params.append(status)
    if q:
        like = f"%{q}%"
        sql += """
            AND (
                a.application_number LIKE ?
                OR c.name LIKE ?
                OR c.mobile LIKE ?
                OR c.email LIKE ?
                OR c.city LIKE ?
            )
        """
        params.extend([like, like, like, like, like])
    sql += " ORDER BY a.submitted_at DESC"
    with _connect() as con:
        return [_row(r) for r in con.execute(sql, params)]


def get_application(application_id: int) -> dict | None:
    with _connect() as con:
        app_row = con.execute(
            """
            SELECT a.*, c.*, j.job_title, j.location AS job_location
            FROM job_applications a
            JOIN candidates c ON c.candidate_id = a.candidate_id
            JOIN jobs j ON j.job_id = a.job_id
            WHERE a.application_id = ?
            """,
            (application_id,),
        ).fetchone()
        if app_row is None:
            return None
        data = _row(app_row)
        data["education"] = [
            _row(r)
            for r in con.execute(
                """
                SELECT * FROM candidate_education
                WHERE candidate_id = ?
                ORDER BY education_id
                """,
                (data["candidate_id"],),
            )
        ]
        data["experience"] = _row(
            con.execute(
                "SELECT * FROM candidate_experience WHERE candidate_id = ? LIMIT 1",
                (data["candidate_id"],),
            ).fetchone()
        )
        data["skills"] = _row(
            con.execute(
                "SELECT * FROM candidate_skills WHERE candidate_id = ? LIMIT 1",
                (data["candidate_id"],),
            ).fetchone()
        )
        data["history"] = [
            _row(r)
            for r in con.execute(
                """
                SELECT * FROM application_status_history
                WHERE application_id = ?
                ORDER BY changed_at
                """,
                (application_id,),
            )
        ]
        data["notes"] = [
            _row(r)
            for r in con.execute(
                """
                SELECT * FROM application_notes
                WHERE application_id = ?
                ORDER BY created_at DESC
                """,
                (application_id,),
            )
        ]
        return data


def resolve_resume(application_id: int) -> tuple[Path, str, str] | None:
    with _connect() as con:
        row = con.execute(
            """
            SELECT resume_stored_name, resume_original_name, resume_file_type
            FROM job_applications
            WHERE application_id = ?
            """,
            (application_id,),
        ).fetchone()
    if row is None or not row["resume_stored_name"]:
        return None
    stored = row["resume_stored_name"]
    if "/" in stored or "\\" in stored or ".." in stored:
        return None
    path = (_upload_dir() / stored).resolve()
    try:
        path.relative_to(_upload_dir().resolve())
    except ValueError:
        return None
    if not path.is_file():
        return None
    return path, row["resume_original_name"] or stored, row["resume_file_type"] or "application/octet-stream"


def summary() -> dict:
    with _connect() as con:
        total = con.execute("SELECT COUNT(*) FROM job_applications").fetchone()[0]
        new = con.execute(
            "SELECT COUNT(*) FROM job_applications WHERE application_status = 'New'"
        ).fetchone()[0]
        return {"total": int(total), "new": int(new)}


def list_jobs() -> list[dict]:
    with _connect() as con:
        return [_row(r) for r in con.execute("SELECT * FROM jobs ORDER BY created_at DESC")]


def source_counts() -> list[dict]:
    with _connect() as con:
        return [
            _row(r)
            for r in con.execute(
                """
                SELECT COALESCE(NULLIF(source, ''), 'Other') AS source, COUNT(*) AS n
                FROM job_applications
                GROUP BY COALESCE(NULLIF(source, ''), 'Other')
                ORDER BY n DESC
                """
            )
        ]


def resolve_application_pdf(application_id: int) -> tuple[Path, str, str] | None:
    with _connect() as con:
        row = con.execute(
            """
            SELECT application_pdf_stored_name, application_pdf_original_name
            FROM job_applications
            WHERE application_id = ?
            """,
            (application_id,),
        ).fetchone()
    if row is None or not row["application_pdf_stored_name"]:
        return None
    stored = row["application_pdf_stored_name"]
    if "/" in stored or "\\" in stored or ".." in stored:
        return None
    bases = [_upload_dir(), _upload_dir().parent / "application_pdfs"]
    for base in bases:
        path = (base / stored).resolve()
        try:
            path.relative_to(base.resolve())
        except ValueError:
            continue
        if path.is_file():
            return (
                path,
                row["application_pdf_original_name"] or stored,
                "application/pdf",
            )
    return None
