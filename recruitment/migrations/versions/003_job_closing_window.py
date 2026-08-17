"""Job application closing time and timezone.

Revision ID: 003_job_closing_window
Revises: 002_admin_notes_interview
Create Date: 2026-08-16
"""

from alembic import op
import sqlalchemy as sa

revision = "003_job_closing_window"
down_revision = "002_admin_notes_interview"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("jobs") as batch:
        batch.add_column(sa.Column("closing_time", sa.String(8), server_default="23:59:59"))
        batch.add_column(sa.Column("timezone", sa.String(80), server_default="Asia/Kolkata"))


def downgrade():
    with op.batch_alter_table("jobs") as batch:
        batch.drop_column("timezone")
        batch.drop_column("closing_time")
