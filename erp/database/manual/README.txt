# Manual / one-shot SQL scripts (NOT auto-applied)
#
# These scripts CHANGE or DELETE data. They are never run by:
#   - update_database.bat
#   - scripts/apply_schema_migrations.py
#   - VPS deploy / vps_pull_update.sh
#   - deployment/apply_migrations.sh
#
# Run only when you intentionally need that fix, after taking a DB backup:
#   sqlcmd -S ... -d JTCSS -i erp/database/manual/<file>.sql
#
# Deploy / push only applies SCHEMA changes (new tables, new/changed columns).
# Existing transaction and master DATA is never overwritten.
