"""HR employee master, offer and appointment letters.

Revision ID: 005_hr_employee_offer_appointment
Revises: 004_application_pdf
Create Date: 2026-08-16
"""

from alembic import op
import sqlalchemy as sa

revision = "005_hr_employee_offer_appointment"
down_revision = "004_application_pdf"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "hr_departments",
        sa.Column("department_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "hr_designations",
        sa.Column("designation_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "hr_employee_number_sequences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("prefix", sa.String(40), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("last_number", sa.Integer(), nullable=False),
        sa.UniqueConstraint("prefix", "year", name="uq_emp_seq_prefix_year"),
    )
    op.create_table(
        "hr_employees",
        sa.Column("employee_id", sa.Integer(), primary_key=True),
        sa.Column("employee_code", sa.String(40), nullable=False),
        sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("candidates.candidate_id"), nullable=False),
        sa.Column("application_id", sa.Integer(), sa.ForeignKey("job_applications.application_id"), nullable=False),
        sa.Column("application_number", sa.String(40), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("father_name", sa.String(200)),
        sa.Column("dob", sa.Date()),
        sa.Column("gender", sa.String(40)),
        sa.Column("mobile", sa.String(20)),
        sa.Column("email", sa.String(254)),
        sa.Column("address", sa.Text()),
        sa.Column("city", sa.String(120)),
        sa.Column("state", sa.String(120)),
        sa.Column("pin_code", sa.String(10)),
        sa.Column("highest_qualification", sa.String(200)),
        sa.Column("last_qualification", sa.String(200)),
        sa.Column("university_board", sa.String(200)),
        sa.Column("passing_year", sa.String(20)),
        sa.Column("percentage_cgpa", sa.String(40)),
        sa.Column("sales_experience", sa.String(80)),
        sa.Column("total_work_experience", sa.String(80)),
        sa.Column("previous_company", sa.String(200)),
        sa.Column("previous_designation", sa.String(200)),
        sa.Column("responsibilities", sa.Text()),
        sa.Column("software_sales_experience", sa.String(200)),
        sa.Column("b2b_sales_experience", sa.String(200)),
        sa.Column("tax_accounting_erp_sales_experience", sa.String(200)),
        sa.Column("joining_date", sa.Date()),
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("hr_departments.department_id")),
        sa.Column("designation_id", sa.Integer(), sa.ForeignKey("hr_designations.designation_id")),
        sa.Column("reporting_manager", sa.String(200)),
        sa.Column("employment_type", sa.String(80)),
        sa.Column("work_location", sa.String(200)),
        sa.Column("probation_period", sa.String(80)),
        sa.Column("probation_end_date", sa.Date()),
        sa.Column("employment_status", sa.String(40), nullable=False),
        sa.Column("salary_ctc", sa.String(80)),
        sa.Column("salary_frequency", sa.String(40)),
        sa.Column("basic_salary", sa.String(80)),
        sa.Column("hra", sa.String(80)),
        sa.Column("allowances", sa.String(200)),
        sa.Column("other_compensation", sa.String(200)),
        sa.Column("compensation_effective_date", sa.Date()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_hr_employees_employee_code", "hr_employees", ["employee_code"], unique=True)
    op.create_index("ix_hr_employees_application_id", "hr_employees", ["application_id"], unique=True)
    op.create_table(
        "hr_employee_documents",
        sa.Column("document_id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("hr_employees.employee_id"), nullable=False),
        sa.Column("document_type", sa.String(80), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("stored_name", sa.String(255), nullable=False),
        sa.Column("uploaded_by", sa.String(200)),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "hr_offer_letters",
        sa.Column("offer_id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("hr_employees.employee_id"), nullable=False),
        sa.Column("application_id", sa.Integer(), sa.ForeignKey("job_applications.application_id"), nullable=False),
        sa.Column("offer_number", sa.String(40), nullable=False, unique=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("offer_date", sa.Date()),
        sa.Column("joining_date", sa.Date()),
        sa.Column("salary_ctc", sa.String(80)),
        sa.Column("probation_period", sa.String(80)),
        sa.Column("offer_status", sa.String(40), nullable=False),
        sa.Column("pdf_stored_name", sa.String(255)),
        sa.Column("pdf_original_name", sa.String(255)),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.Column("generated_by", sa.String(200)),
        sa.Column("accepted_at", sa.DateTime()),
        sa.Column("acceptance_method", sa.String(80)),
        sa.Column("recorded_by", sa.String(200)),
        sa.Column("emailed_at", sa.DateTime()),
        sa.Column("emailed_to", sa.String(254)),
        sa.Column("email_status", sa.String(40)),
    )
    op.create_table(
        "hr_appointment_letters",
        sa.Column("appointment_id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("hr_employees.employee_id"), nullable=False),
        sa.Column("appointment_number", sa.String(40), nullable=False, unique=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("template_version", sa.String(40)),
        sa.Column("appointment_date", sa.Date()),
        sa.Column("joining_date", sa.Date()),
        sa.Column("pdf_stored_name", sa.String(255)),
        sa.Column("pdf_original_name", sa.String(255)),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("issued_by", sa.String(200)),
        sa.Column("emailed_at", sa.DateTime()),
        sa.Column("emailed_to", sa.String(254)),
        sa.Column("email_status", sa.String(40)),
    )
    op.create_table(
        "hr_letter_templates",
        sa.Column("template_id", sa.Integer(), primary_key=True),
        sa.Column("letter_type", sa.String(40), nullable=False),
        sa.Column("section_key", sa.String(80), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
    )


def downgrade():
    op.drop_table("hr_letter_templates")
    op.drop_table("hr_appointment_letters")
    op.drop_table("hr_offer_letters")
    op.drop_table("hr_employee_documents")
    op.drop_table("hr_employees")
    op.drop_table("hr_employee_number_sequences")
    op.drop_table("hr_designations")
    op.drop_table("hr_departments")
