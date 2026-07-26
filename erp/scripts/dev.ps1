$erpRoot = Split-Path -Parent $PSScriptRoot

Set-Location $erpRoot

if (-not (Test-Path ".\.venv\Scripts\Activate.ps1")) {
    Write-Error "Virtual environment not found. Run: python -m venv .venv"
    exit 1
}

.\.venv\Scripts\Activate.ps1

$port = if ($env:FLASK_RUN_PORT) { [int]$env:FLASK_RUN_PORT } elseif ($env:PORT) { [int]$env:PORT } else { 8000 }
$listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($listeners) {
    Write-Warning "Port $port is already in use (PID(s): $($listeners.OwningProcess -join ', ')). Stop other services before starting JTCS ERP."
}

Write-Host "Starting JTCS ERP on http://localhost:$port" -ForegroundColor Cyan
python run.py
