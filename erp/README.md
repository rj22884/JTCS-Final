# JTCS ERP â€” Flask + SQL Server

Database-driven ERP with a **two-table transaction architecture** and **dynamic MenuMaster navigation** (no hardcoded sidebar).

## Stack

- Python Flask 3
- SQL Server (`JTCS\JTCS`, database `JTCSS`)
- SQLAlchemy ORM
- Bootstrap 5 + Bootstrap Icons
- Jinja2 recursive sidebar from `MenuMaster`

## Transaction architecture

| Table | Purpose |
|-------|---------|
| **`JTCSDailyTransaction`** | All business work (ITR, GST, SHCIL, expenses, sales, etc.) |
| **`JtcsBankTransaction`** | **All** money movement (existing table â€” not recreated) |

### Rules

- Master tables (`CustomerMaster`, `WorkTypeMaster`, `PaymentModeMaster`, etc.) are **configuration only**
- Modules never store money in their own tables
- Saving a daily transaction **automatically** creates the matching bank row
- Both saves run in one SQL transaction (commit/rollback together)
- **Contra** entries create two bank rows only (Cash â†” Bank transfer)

### Money mapping

| Movement | `JtcsBankTransaction` column |
|----------|------------------------------|
| Money in (income, sale, receipt) | **Debit** |
| Money out (expense, purchase, payment) | **Credit** |

## Setup

### 1. SQL scripts (run in order)

```text
erp/database/001_create_menu_master.sql
erp/database/002_create_jtcs_daily_transaction.sql
erp/database/003_seed_module_menus.sql
```

Script `003` is **idempotent** â€” safe to re-run. It adds Transactions hub, business modules (GST, DSC, SHCIL, TDS, Accounting, Payroll, Employee, Stock, Court Fee, Stamp), report shortcuts, and admin links.

erp/database/004_auth_production.sql
```

Script `004` adds production auth columns/tables (`CompanyProfile`, `AuthToken`) and extends `Users`.

### 2. Python environment

```powershell
cd "E:\Git\JTCS Final\erp"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python run.py
```

Open [http://localhost:8000](http://localhost:8000) (port **8000 only** â€” configured via `FLASK_RUN_PORT` / `PORT` in `.env`).

If the port is already in use, `scripts/dev.ps1` warns before start. Stop other services on 8000 (e.g. stray FastAPI/uvicorn instances) so only JTCS ERP listens. `run.py` disables the Werkzeug reloader to avoid duplicate Flask listeners in debug mode.

Verify without binding a port:

```powershell
python scripts/verify_app.py
```

## Navigation model

All sidebar items come from **`MenuMaster`** in SQL Server. Admins manage menus at `/admin/menus`.

| Module | Example submenu URL |
|--------|---------------------|
| Transactions | `/transactions/new`, `/transactions/contra` |
| GST | `/transactions/new?work_type=GST&sub_work_type=GSTR-3B` |
| ITR | `/transactions/new?work_type=ITR&sub_work_type=ITR Filing` |
| Reports | `/reports/daily-collection`, `/reports/cash-book`, â€¦ |
| Placeholder pages | `/gst/register`, `/payroll/register`, â€¦ (via `pages` blueprint) |

Query-string prefill on `/transactions/new`:

```text
/transactions/new?work_type=GST&sub_work_type=GSTR-1
```

## UI routes

| Route | Description |
|-------|-------------|
| `/` | Redirects to dashboard (when logged in) |
| `/login`, `/logout` | Authentication |
| `/health` | Health check JSON |
| `/dashboard` | Metrics from both transaction tables |
| `/transactions/new` | Daily transaction entry (supports `?work_type=` / `?sub_work_type=`) |
| `/transactions/contra` | Contra (bank-only) transfer |
| `/reports/` | Report hub |
| `/reports/<key>` | Individual reports |
| `/admin/menus` | Dynamic menu administration (Administrator) |
| `/<path>` | Placeholder pages for MenuMaster URLs (e.g. `/gst/register`) |

### Report keys

`daily-collection`, `cash-book`, `bank-book`, `income`, `expense`, `work-wise`, `customer-ledger`, `payment-mode`, `cash-flow`, `bank-balance`, `outstanding`

## Using TransactionService

```python
from app.services.transaction_service import TransactionService

service = TransactionService()

# Customer pays â‚¹2500 for ITR by Cash
result = service.save_daily_transaction(
    {
        "TransactionDate": "2026-07-05",
        "WorkType": "ITR",
        "SubWorkType": "ITR Filing",
        "IncomeAmount": 2500,
        "PaymentModeID": 1,  # Cash from PaymentModeMaster
        "Description": "ITR filing fee",
    },
    created_by="Admin User",
)
# Creates JTCSDailyTransaction + JtcsBankTransaction (Debit=2500)

# Office rent paid from bank
service.save_daily_transaction(
    {
        "WorkType": "Expenses",
        "ExpenseAmount": 12000,
        "PaymentModeID": 2,
        "Description": "Office rent",
    },
    created_by="Admin User",
)

# Cash deposited to bank (contra â€” bank rows only)
service.save_contra(
    {
        "TransactionDate": "2026-07-05",
        "Amount": 10000,
        "FromPaymentModeID": 1,
        "ToPaymentModeID": 2,
        "Description": "Cash deposit",
    },
    created_by="Admin User",
)

service.delete_daily_transaction(transaction_id=1)
```

## Production authentication

- **No demo users** â€” authentication uses SQL Server `Users` table only
- **First install:** if no active Administrator exists, app redirects to `/setup`
- **Setup fields:** Company Name, Owner Name, Administrator Name, Email, Mobile, Password, Company Logo
- **Login:** Email, Password, Remember Me, Show Password, Forgot Password, Forgot User ID, Register
- **Register:** Pending status until email OTP verified + administrator approval at `/admin/users/pending`
- **Password reset:** Email OTP or secure reset link (configure SMTP in `.env`)

### Auth routes

| Route | Description |
|-------|-------------|
| `/setup` | First-time company + administrator setup |
| `/login` | Production sign-in |
| `/register` | New user registration (pending approval) |
| `/verify-email` | Email OTP verification |
| `/forgot-password` | Password reset request |
| `/reset-password` | OTP or token-based password reset |
| `/forgot-user-id` | Recover email via mobile OTP |
| `/admin/users/pending` | Administrator approval queue |

Configure email in `.env`:

```env
# GoDaddy Titan / Workspace SMTP (SSL on port 465; app also falls back to 587)
MAIL_SERVER=smtpout.secureserver.net
MAIL_PORT=465
MAIL_USE_TLS=False
MAIL_USE_SSL=True
MAIL_USERNAME=admin@jtcsxpert.com
MAIL_PASSWORD=your-titan-mailbox-password
MAIL_DEFAULT_SENDER="Joshi Tax Consultancy & Services <admin@jtcsxpert.com>"
SUPPORT_EMAIL=admin@jtcsxpert.com
SMTP_HEALTH_CHECK_ON_STARTUP=True
# VPS: set to public URL so email links work, e.g. http://203.141.5.68:8000
APP_BASE_URL=http://localhost:8000
```

Test SMTP connectivity (run on the VPS too):

```powershell
python scripts/test_smtp_health.py
```

## UI routes

```text
app/
|-- models/
|   |-- menu_master.py
|   `-- transactions.py
|-- repositories/
|   |-- menu_repository.py
|   `-- transaction_repository.py
|-- services/
|   |-- menu_service.py
|   |-- transaction_service.py
|   |-- dashboard_service.py
|   `-- report_service.py
|-- routes/
|   |-- auth.py
|   |-- dashboard.py
|   |-- transactions.py
|   |-- reports.py
|   |-- menu_admin.py
|   `-- pages.py
`-- templates/
    |-- transactions/
    |-- reports/
    |-- dashboard/
    `-- menu_admin/
database/
|-- 001_create_menu_master.sql
|-- 002_create_jtcs_daily_transaction.sql
`-- 003_seed_module_menus.sql
```

