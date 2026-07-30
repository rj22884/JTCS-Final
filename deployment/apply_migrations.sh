#!/usr/bin/env bash
# =============================================================================
# JTCS ERP — apply_migrations.sh
# SCHEMA-ONLY: applies new numbered SQL scripts from erp/database/.
# Never restores .bak, never runs database/manual/ one-shot data scripts.
# Prefer erp/scripts/apply_schema_migrations.py when Python/pyodbc is available.
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"
load_deploy_env

APP_DIR="${VPS_APP_DIR:-${REPO_ROOT}}"
ERP_DIR="${APP_DIR}/${VPS_ERP_DIR:-erp}"
SQL_DIR="${ERP_DIR}/database"
PY_MIG="${ERP_DIR}/scripts/apply_schema_migrations.py"
VENV="${VPS_VENV_DIR:-${ERP_DIR}/.venv}"

# Prefer Python migrator (same rules on Windows + Linux).
if [[ -f "${PY_MIG}" ]]; then
  if [[ -x "${VENV}/bin/python" ]]; then
    log_info "Running schema-only migrator via venv Python…"
    "${VENV}/bin/python" "${PY_MIG}"
    exit $?
  fi
  if command -v python3 >/dev/null 2>&1; then
    log_info "Running schema-only migrator via python3…"
    python3 "${PY_MIG}"
    exit $?
  fi
fi

if [[ -z "${MSSQL_SERVER:-}" ]]; then
  log_warn "MSSQL_SERVER not set and Python migrator unavailable — skipping SQL migrations"
  exit 0
fi

if ! command -v sqlcmd >/dev/null 2>&1; then
  log_warn "sqlcmd not found — skipping SQL migrations"
  exit 0
fi

SQL_AUTH=()
if [[ -n "${MSSQL_USER:-}" ]]; then
  SQL_AUTH=(-U "${MSSQL_USER}" -P "${MSSQL_PASSWORD:-}")
else
  SQL_AUTH=(-E)
fi

DB="${MSSQL_DATABASE:-JTCSS}"

# One-shot data scripts — never auto-apply (also live under database/manual/).
SKIP_REGEX='^(006_inspect_user_emails|007_cleanup_legacy_users|016_backfill_stamp_payment_lines|034_delete_ecourt_test_stationery|060_ecourt_buy_value_reconcile_old|061_ecourt_purchaseamount_to_shcilecourt)\.sql$'

log_info "Ensuring SchemaMigration table (schema-only deploy)…"
sqlcmd -S "${MSSQL_SERVER}" "${SQL_AUTH[@]}" -d "${DB}" -Q "
IF OBJECT_ID(N'dbo.SchemaMigration', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.SchemaMigration (
    MigrationID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    ScriptName NVARCHAR(260) NOT NULL UNIQUE,
    AppliedAt DATETIME2 NOT NULL CONSTRAINT DF_SchemaMigration_AppliedAt DEFAULT (SYSUTCDATETIME())
  );
END
"

shopt -s nullglob
SCRIPTS=("${SQL_DIR}"/[0-9][0-9][0-9]_*.sql)
if [[ ${#SCRIPTS[@]} -eq 0 ]]; then
  log_info "No SQL scripts found in ${SQL_DIR}"
  exit 0
fi

for script in "${SCRIPTS[@]}"; do
  name="$(basename "${script}")"
  if [[ "${name}" =~ ${SKIP_REGEX} ]]; then
    log_warn "Skipping data-mutation script: ${name}"
    continue
  fi
  if grep -Eiq 'RESTORE[[:space:]]+DATABASE|DROP[[:space:]]+DATABASE|TRUNCATE[[:space:]]+TABLE' "${script}"; then
    log_warn "Skipping dangerous script: ${name}"
    continue
  fi
  exists="$(sqlcmd -S "${MSSQL_SERVER}" "${SQL_AUTH[@]}" -d "${DB}" -h -1 -W -Q \
    "SET NOCOUNT ON; SELECT COUNT(1) FROM dbo.SchemaMigration WHERE ScriptName = N'${name}';" \
    | tr -d '[:space:]')"
  if [[ "${exists}" == "1" ]]; then
    continue
  fi
  log_info "Applying schema script ${name}…"
  if ! sqlcmd -S "${MSSQL_SERVER}" "${SQL_AUTH[@]}" -d "${DB}" -b -i "${script}"; then
    log_error "Migration failed: ${name} (data was not restored/overwritten)"
    exit 1
  fi
  sqlcmd -S "${MSSQL_SERVER}" "${SQL_AUTH[@]}" -d "${DB}" -Q \
    "INSERT INTO dbo.SchemaMigration (ScriptName) VALUES (N'${name}');"
  log_ok "Applied ${name}"
done

log_ok "Database SCHEMA migrations complete (data preserved)"
exit 0
