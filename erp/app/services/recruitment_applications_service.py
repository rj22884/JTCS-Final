"""Read Sales Executive applications from the website recruitment SQLite database."""

from __future__ import annotations

import sqlite3
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
            c.name,
            c.mobile,
            c.email,
            c.city,
            j.job_title
        FROM job_applications a
        JOIN candidates c ON c.candidate_id = a.candidate_id
        JOIN jobs j ON j.job_id = a.job_id
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
