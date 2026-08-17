"""Admin notes and interview fields.

Revision ID: 002_admin_notes_interview
Revises: 001_initial_recruitment
Create Date: 2026-08-16
"""

from alembic import op
import sqlalchemy as sa

revision = "002_admin_notes_interview"
down_revision = "001_initial_recruitment"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("job_applications") as batch:
        batch.add_column(sa.Column("interview_interviewer", sa.String(200)))
        batch.add_column(sa.Column("interview_result", sa.String(40)))
    op.create_table(
        "application_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("application_id", sa.Integer(), sa.ForeignKey("job_applications.application_id"), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_application_notes_application_id", "application_notes", ["application_id"])
    op.create_index("ix_application_notes_created_at", "application_notes", ["created_at"])


def downgrade():
    op.drop_index("ix_application_notes_created_at", table_name="application_notes")
    op.drop_index("ix_application_notes_application_id", table_name="application_notes")
    op.drop_table("application_notes")
    with op.batch_alter_table("job_applications") as batch:
        batch.drop_column("interview_result")
        batch.drop_column("interview_interviewer")
