"""Initial recruitment tables.

Revision ID: 001_initial_recruitment
Revises:
Create Date: 2026-08-16
"""

from alembic import op
import sqlalchemy as sa

revision = "001_initial_recruitment"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "jobs",
        sa.Column("job_id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("job_title", sa.String(200), nullable=False),
        sa.Column("department", sa.String(120)),
        sa.Column("location", sa.String(200)),
        sa.Column("employment_type", sa.String(80)),
        sa.Column("description", sa.Text()),
        sa.Column("about_company", sa.Text()),
        sa.Column("responsibilities", sa.Text()),
        sa.Column("required_skills", sa.Text()),
        sa.Column("experience_required", sa.String(200)),
        sa.Column("qualification_required", sa.String(200)),
        sa.Column("salary_ctc", sa.String(200)),
        sa.Column("benefits", sa.Text()),
        sa.Column("application_instructions", sa.Text()),
        sa.Column("status", sa.String(40)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("closing_date", sa.Date()),
    )
    op.create_index("ix_jobs_slug", "jobs", ["slug"], unique=True)
    op.create_index("ix_jobs_status", "jobs", ["status"])

    op.create_table(
        "candidates",
        sa.Column("candidate_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("father_name", sa.String(200), nullable=False),
        sa.Column("dob", sa.Date(), nullable=False),
        sa.Column("gender", sa.String(30), nullable=False),
        sa.Column("mobile", sa.String(20), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("city", sa.String(120), nullable=False),
        sa.Column("state", sa.String(120), nullable=False),
        sa.Column("pin_code", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_candidates_mobile", "candidates", ["mobile"])
    op.create_index("ix_candidates_email", "candidates", ["email"])
    op.create_index("ix_candidates_city", "candidates", ["city"])

    op.create_table(
        "candidate_education",
        sa.Column("education_id", sa.Integer(), primary_key=True),
        sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("candidates.candidate_id"), nullable=False),
        sa.Column("education_type", sa.String(40), nullable=False),
        sa.Column("qualification", sa.String(200), nullable=False),
        sa.Column("university_board", sa.String(200)),
        sa.Column("passing_year", sa.Integer()),
        sa.Column("percentage_cgpa", sa.String(40)),
    )
    op.create_index("ix_candidate_education_candidate_id", "candidate_education", ["candidate_id"])

    op.create_table(
        "candidate_experience",
        sa.Column("experience_id", sa.Integer(), primary_key=True),
        sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("candidates.candidate_id"), nullable=False),
        sa.Column("sales_experience_years", sa.Integer(), nullable=False),
        sa.Column("sales_experience_months", sa.Integer()),
        sa.Column("previous_company", sa.String(200)),
        sa.Column("previous_designation", sa.String(200)),
        sa.Column("responsibilities", sa.Text()),
        sa.Column("total_work_experience", sa.String(80)),
        sa.Column("software_sales_experience", sa.String(200)),
        sa.Column("b2b_sales_experience", sa.String(200)),
        sa.Column("tax_accounting_erp_sales_experience", sa.String(200)),
    )
    op.create_index("ix_candidate_experience_candidate_id", "candidate_experience", ["candidate_id"])

    op.create_table(
        "candidate_skills",
        sa.Column("skill_id", sa.Integer(), primary_key=True),
        sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("candidates.candidate_id"), nullable=False),
        sa.Column("communication_skills", sa.String(40)),
        sa.Column("computer_knowledge", sa.String(40)),
        sa.Column("ms_excel_knowledge", sa.String(40)),
        sa.Column("crm_erp_knowledge", sa.String(40)),
        sa.Column("digital_marketing_knowledge", sa.String(40)),
        sa.Column("other_skills", sa.Text()),
    )
    op.create_index("ix_candidate_skills_candidate_id", "candidate_skills", ["candidate_id"])

    op.create_table(
        "job_applications",
        sa.Column("application_id", sa.Integer(), primary_key=True),
        sa.Column("application_number", sa.String(40), nullable=False),
        sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("candidates.candidate_id"), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.job_id"), nullable=False),
        sa.Column("application_status", sa.String(40), nullable=False),
        sa.Column("source", sa.String(80)),
        sa.Column("visitor_id", sa.String(64)),
        sa.Column("session_id", sa.String(64)),
        sa.Column("expected_salary", sa.String(80)),
        sa.Column("notice_period", sa.String(80)),
        sa.Column("current_employment_status", sa.String(80)),
        sa.Column("willing_to_work_haldwani", sa.Boolean()),
        sa.Column("willing_to_travel", sa.Boolean()),
        sa.Column("about_candidate", sa.Text()),
        sa.Column("suitability_answer", sa.Text()),
        sa.Column("resume_original_name", sa.String(255)),
        sa.Column("resume_stored_name", sa.String(255)),
        sa.Column("resume_file_reference", sa.String(64)),
        sa.Column("resume_file_type", sa.String(80)),
        sa.Column("resume_file_size", sa.Integer()),
        sa.Column("resume_uploaded_at", sa.DateTime()),
        sa.Column("declaration_accepted", sa.Boolean(), nullable=False),
        sa.Column("interview_scheduled_at", sa.DateTime()),
        sa.Column("interview_mode", sa.String(40)),
        sa.Column("interview_location", sa.String(200)),
        sa.Column("interview_notes", sa.Text()),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_job_applications_application_number", "job_applications", ["application_number"], unique=True)
    op.create_index("ix_job_applications_candidate_id", "job_applications", ["candidate_id"])
    op.create_index("ix_job_applications_job_id", "job_applications", ["job_id"])
    op.create_index("ix_job_applications_application_status", "job_applications", ["application_status"])
    op.create_index("ix_job_applications_visitor_id", "job_applications", ["visitor_id"])
    op.create_index("ix_job_applications_session_id", "job_applications", ["session_id"])
    op.create_index("ix_job_applications_submitted_at", "job_applications", ["submitted_at"])

    op.create_table(
        "application_status_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("application_id", sa.Integer(), sa.ForeignKey("job_applications.application_id"), nullable=False),
        sa.Column("old_status", sa.String(40)),
        sa.Column("new_status", sa.String(40), nullable=False),
        sa.Column("changed_by", sa.String(200)),
        sa.Column("change_reason", sa.String(500)),
        sa.Column("changed_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_application_status_history_application_id", "application_status_history", ["application_id"])
    op.create_index("ix_application_status_history_changed_at", "application_status_history", ["changed_at"])

    op.create_table(
        "recruitment_audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("event_name", sa.String(200), nullable=False),
        sa.Column("candidate_id", sa.Integer()),
        sa.Column("application_id", sa.Integer()),
        sa.Column("session_id", sa.String(64)),
        sa.Column("visitor_id", sa.String(64)),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("user_agent", sa.String(500)),
        sa.Column("device_type", sa.String(40)),
        sa.Column("browser", sa.String(80)),
        sa.Column("operating_system", sa.String(80)),
        sa.Column("referrer", sa.String(500)),
        sa.Column("page_url", sa.String(500)),
        sa.Column("actor_type", sa.String(20)),
        sa.Column("actor_name", sa.String(200)),
        sa.Column("details", sa.Text()),
        sa.Column("event_timestamp", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_recruitment_audit_log_event_type", "recruitment_audit_log", ["event_type"])
    op.create_index("ix_recruitment_audit_log_candidate_id", "recruitment_audit_log", ["candidate_id"])
    op.create_index("ix_recruitment_audit_log_application_id", "recruitment_audit_log", ["application_id"])
    op.create_index("ix_recruitment_audit_log_session_id", "recruitment_audit_log", ["session_id"])
    op.create_index("ix_recruitment_audit_log_visitor_id", "recruitment_audit_log", ["visitor_id"])
    op.create_index("ix_recruitment_audit_log_event_timestamp", "recruitment_audit_log", ["event_timestamp"])

    op.create_table(
        "application_number_sequences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("prefix", sa.String(40), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("last_number", sa.Integer(), nullable=False),
        sa.UniqueConstraint("prefix", "year", name="uq_app_seq_prefix_year"),
    )

    op.create_table(
        "admin_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(40), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_login_at", sa.DateTime()),
    )
    op.create_index("ix_admin_users_email", "admin_users", ["email"], unique=True)

    op.create_table(
        "recruitment_settings",
        sa.Column("key", sa.String(80), primary_key=True),
        sa.Column("value", sa.Text()),
    )


def downgrade():
    op.drop_table("recruitment_settings")
    op.drop_table("admin_users")
    op.drop_table("application_number_sequences")
    op.drop_table("recruitment_audit_log")
    op.drop_table("application_status_history")
    op.drop_table("job_applications")
    op.drop_table("candidate_skills")
    op.drop_table("candidate_experience")
    op.drop_table("candidate_education")
    op.drop_table("candidates")
    op.drop_table("jobs")
