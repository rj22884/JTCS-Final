# JTCS Final

This workspace contains:

| Folder | Description |
|--------|-------------|
| **`erp/`** | **JTCS ERP** — Flask + SQL Server + dynamic `MenuMaster` navigation |
| `backend/` | Legacy FastAPI starter (optional) |
| `frontend/` | Legacy React starter (optional) |

## Start the ERP

```powershell
cd "E:\Git\JTCS Final\erp"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Run SQL script: `erp/database/001_create_menu_master.sql`

```powershell
python run.py
```

Open [http://localhost:8000](http://localhost:8000)

See **`erp/README.md`** for full documentation.
"# JTCS-final" 
