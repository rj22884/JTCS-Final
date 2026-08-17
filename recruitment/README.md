# JTCS Recruitment — standalone module

This is a **separate Flask app**. It does not serve the marketing website and it is not part of the ERP (`E:\Git\JTCS Final\erp`).

- Website (static): `D:\JTCS Web Page` on `http://localhost:5500`
- ERP: `E:\Git\JTCS Final` on `http://localhost:8000`
- Recruitment: this folder on `http://127.0.0.1:5050`

Canonical copy for local/app use: `E:\Git\JTCS Final\recruitment`

## How to run (Windows)

```bat
cd /d "E:\Git\JTCS Final\recruitment"
start.bat
```

Or from the website copy:

```bat
cd /d "D:\JTCS Web Page\recruitment"
start.bat
```

Then open:

- Apply form: http://127.0.0.1:5050/careers/apply/sales-executive
- Application status: http://127.0.0.1:5050/careers/application-status
- Admin: http://127.0.0.1:5050/recruitment/admin/login

First start creates `.venv`, installs requirements, copies `.env.example` → `.env`, and runs `init-db`.

Change `RECRUITMENT_ADMIN_PASSWORD` in `.env` before using admin.

## Manual run

```bat
cd /d "E:\Git\JTCS Final"
python -m venv recruitment\.venv
recruitment\.venv\Scripts\activate
pip install -r recruitment\requirements.txt
copy recruitment\.env.example recruitment\.env
flask --app recruitment init-db
python -m recruitment
```

## What this app serves

Only:

- `/careers/...` public apply / status / confirmation
- `/recruitment/...` admin + HR
- `/api/recruitment/...`
- `/recruitment/static/...`
- `/healthz`

It does **not** serve `index.html`, `/pages/`, or website `/assets/`.

## Remove later

Website bridge files (safe to delete when hiring is over):

- `D:\JTCS Web Page\assets\js\recruitment-cta.js`
- `D:\JTCS Web Page\assets\js\recruitment-apply.js`
- `D:\JTCS Web Page\assets\css\recruitment.css`
- `D:\JTCS Web Page\pages\careers-sales-executive.html`
- `initRecruitmentCta()` in `assets\js\main.js`
- `recruitment.css` link in `index.html`
- `D:\JTCS Web Page\recruitment\` (if unused)
- `vps\nginx-recruitment.conf`, `deploy_recruitment.bat`

App module:

- `E:\Git\JTCS Final\recruitment\`
- launcher option 7 in `j.bat`

ERP “Sales Executive Applications” menu (`/admin/recruitment`) is a reader for this module’s database — remove that separately if needed.
