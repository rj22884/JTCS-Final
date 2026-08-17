"""Store generated application PDFs.

Revision ID: 004_application_pdf
Revises: 003_job_closing_window
Create Date: 2026-08-16
"""

from alembic import op
import sqlalchemy as sa

revision = "004_application_pdf"
down_revision = "003_job_closing_window"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("job_applications") as batch:
        batch.add_column(sa.Column("application_pdf_stored_name", sa.String(255)))
        batch.add_column(sa.Column("application_pdf_original_name", sa.String(255)))
        batch.add_column(sa.Column("application_pdf_generated_at", sa.DateTime()))


def downgrade():
    with op.batch_alter_table("job_applications") as batch:
        batch.drop_column("application_pdf_generated_at")
        batch.drop_column("application_pdf_original_name")
        batch.drop_column("application_pdf_stored_name")
