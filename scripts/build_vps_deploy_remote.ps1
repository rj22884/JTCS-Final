# Builds a Unix-LF remote deploy script for SSH "bash -s".
# Usage:
#   powershell -File scripts\build_vps_deploy_remote.ps1 -OutFile PATH -RepoPath /root/JTCS-final -Branch main

param(
    [Parameter(Mandatory = $true)][string]$OutFile,
    [Parameter(Mandatory = $true)][string]$RepoPath,
    [Parameter(Mandatory = $true)][string]$Branch
)

$ErrorActionPreference = "Stop"
$repo = ($RepoPath -replace "`r", "").Trim()
$branch = ($Branch -replace "`r", "").Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { $repo = "/root/JTCS-final" }
if ([string]::IsNullOrWhiteSpace($branch)) { $branch = "main" }
if ($repo -eq "~/JTCS-final" -or $repo -eq "~/JTCS-Final") { $repo = "/root/JTCS-final" }

$nl = "`n"
$lines = @(
    "set -e",
    "REPO='$repo'",
    'case "$REPO" in ~/*) REPO="$HOME${REPO#~}";; esac',
    'if [ ! -d "$REPO" ]; then',
    '  echo "ERROR: folder missing: $REPO"',
    '  ls -la "$HOME" || true',
    "  exit 1",
    "fi",
    'cd "$REPO"',
    'echo "== VPS deploy start =="',
    'echo "PWD=$(pwd)"',
    "export BRANCH='$branch'",
    'echo "BRANCH=$BRANCH"',
    "git fetch origin",
    'if [ ! -f scripts/vps_pull_update.sh ]; then',
    '  echo "pull script missing — resetting code from origin"',
    '  if [ -f erp/.env ]; then cp erp/.env /tmp/jtcs.env.bak; fi',
    "  git checkout -B '$branch' 'origin/$branch' 2>/dev/null || git checkout '$branch' || git checkout main",
    "  git reset --hard 'origin/$branch' 2>/dev/null || git reset --hard origin/main",
    '  if [ -f /tmp/jtcs.env.bak ]; then cp /tmp/jtcs.env.bak erp/.env; fi',
    "fi",
    'if [ -f scripts/vps_pull_update.sh ]; then',
    "  bash scripts/vps_pull_update.sh",
    "else",
    '  echo "ERROR: scripts/vps_pull_update.sh still missing after fetch"',
    "  ls -la",
    "  exit 1",
    "fi",
    'echo "== VPS deploy OK =="'
)

[System.IO.File]::WriteAllText($OutFile, ($lines -join $nl) + $nl)
Write-Output $OutFile
