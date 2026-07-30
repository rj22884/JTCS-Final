#!/usr/bin/env bash
# =============================================================================
# JTCS ERP — apply_migrations.sh
# Applies new numbered SQL scripts from erp/database/ using sqlcmd when configured.
# Tracks applied files in dbo.SchemaMigration (created if missing).
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"
load_deploy_env

APP_DIR="${VPS_APP_DIR:-${REPO_ROOT}}"
ERP_DIR="${APP_DIR}/${VPS_ERP_DIR:-erp}"
SQL_DIR="${ERP_DIR}/database"

if [[ -z "${MSSQL_SERVER:-}" ]]; then
  log_warn "MSSQL_SERVER not set — skipping SQL migrations"
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

log_info "Ensuring SchemaMigration table…"
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
  exists="$(sqlcmd -S "${MSSQL_SERVER}" "${SQL_AUTH[@]}" -d "${DB}" -h -1 -W -Q \
    "SET NOCOUNT ON; SELECT COUNT(1) FROM dbo.SchemaMigration WHERE ScriptName = N'${name}';" \
    | tr -d '[:space:]')"
  if [[ "${exists}" == "1" ]]; then
    continue
  fi
  log_info "Applying ${name}…"
  if ! sqlcmd -S "${MSSQL_SERVER}" "${SQL_AUTH[@]}" -d "${DB}" -b -i "${script}"; then
    log_error "Migration failed: ${name}"
    exit 1
  fi
  sqlcmd -S "${MSSQL_SERVER}" "${SQL_AUTH[@]}" -d "${DB}" -Q \
    "INSERT INTO dbo.SchemaMigration (ScriptName) VALUES (N'${name}');"
  log_ok "Applied ${name}"
done

log_ok "Database migrations complete"
exit 0
