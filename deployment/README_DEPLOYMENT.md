# JTCS ERP — One-Click Deployment

Production-ready Windows → GitHub → Ubuntu VPS pipeline with backups, rollback, health checks, and enterprise version management.

## Quick start (Windows)

1. Double-click `deployment\setup_deployment.bat`
2. Edit `deployment\deploy.env` (never commit this file)
3. On the VPS, run `bash deployment/setup_deployment.sh` once
4. Double-click `deployment\deploy.bat` whenever you want to ship

Empty commit message → **Auto Deployment**.

## Files

| File | Role |
|------|------|
| `deploy.bat` | One-click: commit → push → SSH deploy |
| `deploy.sh` | VPS: backup → pull → migrate → restart → health |
| `backup.sh` | App + config + uploads + SQL backup |
| `rollback.sh` | Restore by `--latest`, `--version`, or `--backup` |
| `healthcheck.sh` | Gunicorn, Nginx, HTTP, DB |
| `setup_deployment.bat` / `.sh` | First-time setup |
| `record_version.py` | Writes `dbo.AppVersionHistory` |
| `apply_migrations.sh` | Applies `erp/database/NNN_*.sql` |
| `github-actions.yml` | CI/CD on push to `main` |
| `config/*` | env example, nginx, systemd, gunicorn |

## Version UI

- Login footer + app status bar show **Version X.Y.Z**
- Admin → **Software Updates** / **About Software**
- SQL: `erp/database/066_app_version_management.sql`

## Security

- No passwords in scripts
- Secrets only in `deploy.env` / GitHub Actions secrets / SSH keys
- `deploy.env` is gitignored

See **DEPLOYMENT_GUIDE.md** for SSH, Actions, rollback, and troubleshooting.
