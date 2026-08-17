"""Ensure new admin tables/columns exist on the current recruitment database."""

from __future__ import annotations

from sqlalchemy import inspect, text

from recruitment.extensions import db


def ensure_admin_schema() -> None:
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())
    if "job_applications" not in tables:
        return

    job_columns = {col["name"] for col in inspector.get_columns("jobs")} if "jobs" in tables else set()
    columns = {col["name"] for col in inspector.get_columns("job_applications")}
    with db.engine.begin() as conn:
        if "jobs" in tables and "closing_time" not in job_columns:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN closing_time VARCHAR(8) DEFAULT '23:59:59'"))
        if "jobs" in tables and "timezone" not in job_columns:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN timezone VARCHAR(80) DEFAULT 'Asia/Kolkata'"))
        if "interview_interviewer" not in columns:
            conn.execute(text("ALTER TABLE job_applications ADD COLUMN interview_interviewer VARCHAR(200)"))
        if "interview_result" not in columns:
            conn.execute(text("ALTER TABLE job_applications ADD COLUMN interview_result VARCHAR(40)"))
        if "application_pdf_stored_name" not in columns:
            conn.execute(text("ALTER TABLE job_applications ADD COLUMN application_pdf_stored_name VARCHAR(255)"))
        if "application_pdf_original_name" not in columns:
            conn.execute(text("ALTER TABLE job_applications ADD COLUMN application_pdf_original_name VARCHAR(255)"))
        if "application_pdf_generated_at" not in columns:
            conn.execute(text("ALTER TABLE job_applications ADD COLUMN application_pdf_generated_at DATETIME"))
        if "application_notes" not in tables:
            conn.execute(
                text(
                    """
                    CREATE TABLE application_notes (
                        id INTEGER PRIMARY KEY,
                        application_id INTEGER NOT NULL,
                        note TEXT NOT NULL,
                        created_by VARCHAR(200) NOT NULL,
                        created_at DATETIME NOT NULL,
                        FOREIGN KEY(application_id) REFERENCES job_applications (application_id)
                    )
                    """
                )
            )
            conn.execute(text("CREATE INDEX ix_application_notes_application_id ON application_notes (application_id)"))
            conn.execute(text("CREATE INDEX ix_application_notes_created_at ON application_notes (created_at)"))

    from recruitment.job_window import ensure_sales_executive_closing
    from recruitment.models import Job
    from recruitment.seed import seed_hr_defaults

    db.create_all()
    seed_hr_defaults()

    job = Job.query.filter_by(slug="sales-executive").first()
    if job is not None:
        ensure_sales_executive_closing(job)
        db.session.commit()
    else:
        db.session.commit()
