#Requires -Version 5.1
<#
.SYNOPSIS
  Auto-backup JTCS project to D:\JTCS Backup whenever files change.

.DESCRIPTION
  Watches the repo for changes (debounced), then copies a clean snapshot to:
    D:\JTCS Backup\Auto\JTCS_yyyyMMdd_HHmmss\

  Modes:
    -Watch          Keep running and backup after changes (default)
    -Once           Take one backup and exit
    -InstallStartup Register Windows logon task so watcher starts automatically
    -UninstallStartup Remove the logon task
    -Status         Show whether watcher is running
#>
[CmdletBinding()]
param(
    [string]$Source = "",
    [string]$BackupRoot = "D:\JTCS Backup",
    [int]$DebounceSeconds = 120,
    [int]$KeepLast = 20,
    [switch]$Once,
    [switch]$Watch,
    [switch]$InstallStartup,
    [switch]$UninstallStartup,
    [switch]$Status
)

$ErrorActionPreference = "Stop"

if (-not $Source) {
    $Source = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
$Source = (Resolve-Path $Source).Path
$AutoDir = Join-Path $BackupRoot "Auto"
$LogFile = Join-Path $BackupRoot "auto_backup.log"
$PidFile = Join-Path $BackupRoot "auto_backup.pid"
$TaskName = "JTCS Local Auto Backup"

$ExcludeDirs = @(
    ".venv", "venv", "node_modules", "__pycache__", ".git",
    ".cursor", ".pytest_cache", ".mypy_cache", "deployment\logs",
    "erp\backups", "backups", "instance", ".idea", ".vscode"
)
$ExcludeFiles = @("*.pyc", "*.pyo", "*.log", "*.tmp", "Thumbs.db", "desktop.ini")

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $line = "{0:yyyy-MM-dd HH:mm:ss} [{1}] {2}" -f (Get-Date), $Level, $Message
    try {
        if (-not (Test-Path $BackupRoot)) {
            New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
        }
        Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
    } catch { }
    Write-Host $line
}

function Ensure-Folders {
    if (-not (Test-Path "D:\")) {
        throw "Drive D: not found. Cannot use backup path: $BackupRoot"
    }
    New-Item -ItemType Directory -Force -Path $BackupRoot, $AutoDir | Out-Null
}

function Get-WatcherPid {
    if (-not (Test-Path $PidFile)) { return $null }
    $raw = (Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if (-not $raw) { return $null }
    $procId = 0
    if (-not [int]::TryParse($raw.Trim(), [ref]$procId)) { return $null }
    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($null -eq $proc) { return $null }
    # Confirm it looks like our powershell watcher
    try {
        $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue).CommandLine
        if ($cmd -and ($cmd -like "*local_auto_backup.ps1*")) { return $procId }
    } catch { }
    return $null
}

function Stop-StalePidFile {
    $alive = Get-WatcherPid
    if ($null -eq $alive -and (Test-Path $PidFile)) {
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-ProjectBackup {
    param([string]$Reason = "manual")
    Ensure-Folders
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $dest = Join-Path $AutoDir ("JTCS_" + $stamp)
    New-Item -ItemType Directory -Force -Path $dest | Out-Null

    $xd = ($ExcludeDirs | ForEach-Object { "/XD"; $_ })
    $xf = ($ExcludeFiles | ForEach-Object { "/XF"; $_ })
    Write-Log "Backup start ($Reason) -> $dest"

    # Use call operator (not Start-Process) so paths with spaces stay intact.
    $rcArgs = @(
        $Source, $dest,
        "/E", "/R:1", "/W:1", "/NFL", "/NDL", "/NJH", "/NJS", "/NP", "/XJ",
        "/MT:8"
    ) + $xd + $xf
    & robocopy.exe @rcArgs | Out-Null
    $rc = $LASTEXITCODE
    # robocopy: 0-7 = success-ish
    if ($rc -ge 8) {
        Write-Log "robocopy failed with exit $rc" "ERROR"
        throw "Backup failed (robocopy exit $rc)"
    }

    # Small marker for restore clarity
    @"
JTCS Auto Backup
Source : $Source
Created: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Reason : $Reason
"@ | Set-Content -LiteralPath (Join-Path $dest "BACKUP_INFO.txt") -Encoding UTF8

    # Retention
    $dirs = Get-ChildItem -LiteralPath $AutoDir -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "JTCS_*" } |
        Sort-Object Name -Descending
    if ($dirs.Count -gt $KeepLast) {
        $dirs | Select-Object -Skip $KeepLast | ForEach-Object {
            Write-Log "Removing old backup: $($_.FullName)"
            Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    Write-Log "Backup OK: $dest"
    return $dest
}

function Start-WatcherLoop {
    Ensure-Folders
    Stop-StalePidFile
    $existing = Get-WatcherPid
    if ($null -ne $existing) {
        Write-Log "Watcher already running (PID $existing). Exit."
        return
    }

    $PID | Set-Content -LiteralPath $PidFile -Encoding ASCII
    Write-Log "Watcher started. Source=$Source  Dest=$AutoDir  Debounce=${DebounceSeconds}s  PID=$PID"

    # Initial snapshot so folder is never empty
    try { Invoke-ProjectBackup -Reason "startup" | Out-Null } catch {
        Write-Log "Startup backup failed: $($_.Exception.Message)" "WARN"
    }

    $script:pending = $false
    $script:lastChange = Get-Date

    $watcher = New-Object System.IO.FileSystemWatcher
    $watcher.Path = $Source
    $watcher.IncludeSubdirectories = $true
    $watcher.NotifyFilter = [IO.NotifyFilters]::FileName -bor `
        [IO.NotifyFilters]::DirectoryName -bor `
        [IO.NotifyFilters]::LastWrite -bor `
        [IO.NotifyFilters]::Size
    $watcher.EnableRaisingEvents = $true

    $handler = {
        param($sender, $eventArgs)
        $name = [string]$eventArgs.Name
        if ([string]::IsNullOrWhiteSpace($name)) { return }
        $lower = $name.ToLowerInvariant().Replace('/', '\')
        # Skip noisy / regenerable paths
        if ($lower -match '(^|\\)(\.venv|venv|node_modules|__pycache__|\.git|\.cursor|deployment\\logs|erp\\backups)(\\|$)' -or
            $lower -match '\.(pyc|pyo|log|tmp)$') {
            return
        }
        $script:pending = $true
        $script:lastChange = Get-Date
    }

    $handlers = @()
    foreach ($evt in @("Changed", "Created", "Deleted", "Renamed")) {
        $handlers += Register-ObjectEvent -InputObject $watcher -EventName $evt -Action $handler
    }

    try {
        while ($true) {
            Start-Sleep -Seconds 5
            if ($script:pending) {
                $idle = (Get-Date) - $script:lastChange
                if ($idle.TotalSeconds -ge $DebounceSeconds) {
                    $script:pending = $false
                    try {
                        Invoke-ProjectBackup -Reason "file-change" | Out-Null
                    } catch {
                        Write-Log "Change backup failed: $($_.Exception.Message)" "ERROR"
                    }
                }
            }
        }
    } finally {
        foreach ($h in $handlers) {
            Unregister-Event -SourceIdentifier $h.Name -ErrorAction SilentlyContinue
            Remove-Job -Id $h.Id -Force -ErrorAction SilentlyContinue
        }
        $watcher.EnableRaisingEvents = $false
        $watcher.Dispose()
        if ((Test-Path $PidFile) -and ((Get-Content $PidFile -ErrorAction SilentlyContinue) -eq "$PID")) {
            Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        }
        Write-Log "Watcher stopped (PID $PID)"
    }
}

function Get-StartupShortcutPath {
    $startup = [Environment]::GetFolderPath("Startup")
    return (Join-Path $startup "JTCS Local Auto Backup.lnk")
}

function Install-StartupTask {
    Ensure-Folders
    $ps1 = Join-Path $PSScriptRoot "local_auto_backup.ps1"
    $launcher = Join-Path $PSScriptRoot "run_local_auto_backup_watch.bat"
    if (-not (Test-Path -LiteralPath $launcher)) {
        throw "Missing launcher: $launcher"
    }

    # Prefer per-user Startup folder shortcut (no admin). Fall back to schtasks.
    $lnkPath = Get-StartupShortcutPath
    try {
        $wsh = New-Object -ComObject WScript.Shell
        $sc = $wsh.CreateShortcut($lnkPath)
        $sc.TargetPath = $launcher
        $sc.WorkingDirectory = (Split-Path $launcher -Parent)
        $sc.WindowStyle = 7
        $sc.Description = "JTCS project auto-backup to D:\JTCS Backup"
        $sc.Save()
        Write-Log "Installed Startup shortcut: $lnkPath"
    } catch {
        Write-Log "Startup shortcut failed: $($_.Exception.Message)" "WARN"
        $create = schtasks /Create /TN "$TaskName" /TR "`"$launcher`"" /SC ONLOGON /RL LIMITED /F 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Log "schtasks create failed: $create" "ERROR"
            throw "Failed to install startup. $create"
        }
        Write-Log "Installed startup task: $TaskName -> $launcher"
    }

    # Also start watcher now (single-instance guard inside -Watch)
    # Single ArgumentList string — PS 5.1 splits array args on spaces incorrectly.
    $startArgs = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}" -Watch -Source "{1}" -BackupRoot "{2}"' -f $ps1, $Source, $BackupRoot
    Start-Process -FilePath "powershell.exe" -ArgumentList $startArgs -WindowStyle Hidden
    Start-Sleep -Seconds 3
    Write-Host "[PASS] Auto-backup will start at Windows logon and is running now."
    Write-Host "       Folder: $AutoDir"
}

function Uninstall-StartupTask {
    $lnkPath = Get-StartupShortcutPath
    if (Test-Path -LiteralPath $lnkPath) {
        Remove-Item -LiteralPath $lnkPath -Force -ErrorAction SilentlyContinue
        Write-Log "Removed Startup shortcut: $lnkPath"
    }
    schtasks /Delete /TN $TaskName /F 2>$null | Out-Null
    $alive = Get-WatcherPid
    if ($null -ne $alive) {
        Stop-Process -Id $alive -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    Write-Log "Uninstalled startup and stopped watcher"
    Write-Host "[PASS] Auto-backup startup removed."
}

# ---- main ----
Ensure-Folders

if ($UninstallStartup) {
    Uninstall-StartupTask
    exit 0
}
if ($InstallStartup) {
    Install-StartupTask
    exit 0
}
if ($Status) {
    $alive = Get-WatcherPid
    if ($null -ne $alive) {
        Write-Host "[PASS] Auto-backup watcher running (PID $alive)"
        Write-Host "       Backup folder: $AutoDir"
    } else {
        Write-Host "[INFO] Auto-backup watcher is NOT running"
    }
    if (Test-Path $LogFile) {
        Write-Host "------- last log lines -------"
        Get-Content -LiteralPath $LogFile -Tail 12
    }
    exit 0
}

if ($Once -or (-not $Watch -and -not $Once)) {
    # Default if neither switch: if -Once explicitly OR called without -Watch for one-shot from menu
}

if ($Once) {
    $dest = Invoke-ProjectBackup -Reason "once"
    Write-Host "[PASS] Backup saved: $dest"
    exit 0
}

if ($Watch) {
    Start-WatcherLoop
    exit 0
}

# No mode flags: take one backup (safe default for double-click)
$dest = Invoke-ProjectBackup -Reason "manual"
Write-Host "[PASS] Backup saved: $dest"
