$projectRoot = Split-Path -Parent $PSScriptRoot
$nodePath = "$env:ProgramFiles\nodejs"

if (Test-Path $nodePath) {
    $env:Path = "$nodePath;$env:Path"
}

Write-Host "Starting JTCS ERP (Flask) on http://127.0.0.1:8000" -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$projectRoot\erp'; .\.venv\Scripts\Activate.ps1; python run.py"
)

Start-Sleep -Seconds 2

Write-Host "Starting JTCS Final frontend on http://127.0.0.1:5173" -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$projectRoot\frontend'; npm run dev -- --host 127.0.0.1 --port 5173"
)

Write-Host ""
Write-Host "Open http://localhost:5173 in your browser." -ForegroundColor Green
