# JTCS ERP — Deployment Guide

## 1. Configure SSH (Windows → Ubuntu)

### Generate a deploy key (Windows PowerShell)

```powershell
ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\jtcs_deploy_ed25519 -C "jtcs-deploy"
type $env:USERPROFILE\.ssh\jtcs_deploy_ed25519.pub
```

### Install the public key on the VPS

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo "PASTE_PUBLIC_KEY_HERE" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

### Test

```powershell
ssh -i $env:USERPROFILE\.ssh\jtcs_deploy_ed25519 deploy@YOUR_VPS_IP
```

### `deployment/deploy.env`

```ini
VPS_SSH_HOST=deploy@YOUR_VPS_IP
VPS_SSH_KEY=%USERPROFILE%\.ssh\jtcs_deploy_ed25519
VPS_SSH_PORT=22
VPS_APP_DIR=/var/www/jtcs-erp
HEALTH_URL=http://127.0.0.1:8000/health
```

Never put SQL or mailbox passwords in git. Use `erp/.env` on the VPS (mode `600`).

---

## 2. First-time VPS setup

```bash
sudo mkdir -p /var/www
sudo git clone git@github.com:rj22884/JTCS-final.git /var/www/jtcs-erp
cd /var/www/jtcs-erp
bash deployment/setup_deployment.sh
cp erp/.env.example erp/.env   # edit DB + SECRET_KEY + MAIL_*
cp deployment/config/deploy.env.example deployment/deploy.env
chmod 600 erp/.env deployment/deploy.env
# Edit systemd unit paths if needed, then:
sudo systemctl enable --now jtcs-erp
sudo nginx -t && sudo systemctl reload nginx
```

Apply version SQL once (or let `apply_migrations.sh` do it on next deploy):

```bash
sqlcmd -S "$MSSQL_SERVER" -d JTCSS -i erp/database/066_app_version_management.sql
```

---

## 3. Run deployment (Windows)

1. Finish coding in Cursor / VS Code  
2. Double-click **`deployment\deploy.bat`**  
3. Enter commit message (blank → `Auto Deployment`)  
4. Enter version (e.g. `1.0.1`), release notes, developer  
5. Script commits, tags `v1.0.1`, pushes, SSHs, runs `deploy.sh`

Remote `deploy.sh` will:

1. Backup app/config/uploads/DB → `Version_1.0.1_<timestamp>`  
2. `git pull --ff-only`  
3. `pip install` if `requirements.txt` changed  
4. Apply new SQL migrations  
5. Record version + change log in SQL Server  
6. Restart Gunicorn, reload Nginx  
7. Health check — **auto-rollback on failure**

---

## 4. GitHub Actions

1. Repo → **Settings → Secrets and variables → Actions**  
2. Add secrets:

| Secret | Example |
|--------|---------|
| `VPS_SSH_HOST` | `deploy@203.0.113.10` |
| `VPS_SSH_KEY` | Full private key PEM |
| `VPS_SSH_PORT` | `22` (optional) |
| `VPS_APP_DIR` | `/var/www/jtcs-erp` |

3. Workflow file: `.github/workflows/deploy.yml` (mirror: `deployment/github-actions.yml`)  
4. Push to `main` or run **Actions → Deploy JTCS ERP → Run workflow**

---

## 5. Rollback

### By version

```bash
cd /var/www/jtcs-erp
bash deployment/rollback.sh --version 1.0.0
```

### By latest backup

```bash
bash deployment/rollback.sh --latest
```

### By exact folder

```bash
bash deployment/rollback.sh --backup /var/backups/jtcs-erp/Version_1.0.0_2026-07-29_103000
```

Rollback restores application files, `.env`, uploads, and SQL `.bak` when configured, then restarts services and health-checks.

From **Admin → Software Updates**, the Rollback button shows the exact VPS command (no passwords stored in the web app).

---

## 6. Restore a backup manually

Backups live under `$VPS_BACKUP_ROOT` (default `/var/backups/jtcs-erp/`):

```
Version_1.0.1_2026-07-29_103000/
  app/          # full tree snapshot
  config/       # erp.env, deploy.env, nginx/systemd copies
  uploads/
  sql/*.bak
  MANIFEST.txt
```

SQL restore example:

```bash
sqlcmd -S "$MSSQL_SERVER" -Q "RESTORE DATABASE [JTCSS] FROM DISK = N'/path/to/file.bak' WITH REPLACE"
```

---

## 7. Health check

```bash
bash deployment/healthcheck.sh
curl -fsS http://127.0.0.1:8000/health
systemctl status jtcs-erp nginx
```

Admin UI: **Software Updates → Health Check**.

---

## 8. Troubleshooting

| Symptom | What to check |
|---------|----------------|
| Git push fails | Credentials / branch protection / network — deploy stops |
| SSH fails | Key path, `VPS_SSH_HOST`, firewall port 22, `BatchMode` |
| Git pull fails | Dirty tree on VPS, non-ff history — auto-rollback |
| Gunicorn restart fails | `journalctl -u jtcs-erp -n 100` — auto-rollback |
| Health fails | App logs, DB `.env`, nginx upstream — auto-rollback |
| Migration fails | `sqlcmd` install, `MSSQL_*` in `deploy.env`, script syntax |
| Version not showing | Apply `066_app_version_management.sql`, redeploy once |
| Tag already exists | Choose a new version or delete remote tag carefully |

Logs:

- `/var/log/jtcs-erp/deploy_*.log`
- `/var/log/jtcs-erp/deploy_history.log`
- `/var/log/jtcs-erp/backup.log`
- `/var/log/jtcs-erp/rollback_*.log`

---

## 9. Version management summary

Each successful deploy stores:

- Application + database version, build number  
- Git commit / branch, developer, release notes  
- What's New / Bug Fixes / Features / DB / Security / Performance  
- Backup path + deployment status  

Displayed on:

- Login footer  
- App status bar  
- Admin Dashboard menus → Software Updates / About Software  

Git tags: `v1.0.0`, `v1.0.1`, … pushed by `deploy.bat` when a version is entered.
