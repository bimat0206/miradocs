# ============================================================
# MiraDocs — Cleanup Script (Windows PowerShell)
# Usage:
#   .\cleanup.ps1              — interactive menu
#   .\cleanup.ps1 -Packages    — remove .venv + node_modules only
#   .\cleanup.ps1 -Cache       — remove build/cache artifacts only
#   .\cleanup.ps1 -All         — packages + cache (not data)
#   .\cleanup.ps1 -Data        — delete all user document data
#   .\cleanup.ps1 -Full        — everything (packages + cache + data)
# ============================================================

param(
    [switch]$Packages,
    [switch]$Cache,
    [switch]$All,
    [switch]$Data,
    [switch]$Full
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

# ── Colour helpers ──────────────────────────────────────────
function Write-Ok($msg)      { Write-Host "  v  $msg" -ForegroundColor Green }
function Write-Warn($msg)    { Write-Host "  !  $msg" -ForegroundColor Yellow }
function Write-Info($msg)    { Write-Host "  i  $msg" -ForegroundColor Cyan }
function Write-Header($msg)  { Write-Host "`n== $msg ==" -ForegroundColor Cyan }
function Write-Removed($msg) { Write-Host "  x  Removed: $msg" -ForegroundColor Red }

# ── Flags ───────────────────────────────────────────────────
$DoPackages = $Packages -or $All -or $Full
$DoCache    = $Cache    -or $All -or $Full
$DoData     = $Data     -or $Full
$Interactive = -not ($Packages -or $Cache -or $All -or $Data -or $Full)

$RemovedCount = 0

# ── Interactive menu ─────────────────────────────────────────
if ($Interactive) {
    Write-Host ""
    Write-Host "  MiraDocs — Cleanup" -ForegroundColor Cyan
    Write-Host "  What would you like to remove?"
    Write-Host ""
    Write-Host "  1) Installed packages      (.venv, frontend\node_modules)"
    Write-Host "  2) Build / cache artifacts  (.next, __pycache__, .pytest_cache, tsconfig.tsbuildinfo)"
    Write-Host "  3) Both 1 + 2               (full reset — re-run setup.ps1 to restore)"
    Write-Host "  4) User data                (documents, parsed output, registry.db)"
    Write-Host "  5) Everything               (1 + 2 + 4)"
    Write-Host "  q) Quit"
    Write-Host ""
    $Choice = Read-Host "  Choice [1-5 / q]"

    switch ($Choice) {
        "1" { $DoPackages = $true }
        "2" { $DoCache = $true }
        "3" { $DoPackages = $true; $DoCache = $true }
        "4" { $DoData = $true }
        "5" { $DoPackages = $true; $DoCache = $true; $DoData = $true }
        { $_ -in "q","Q" } { Write-Host ""; Write-Info "Nothing removed."; exit 0 }
        default { Write-Host "  Invalid choice." -ForegroundColor Red; exit 1 }
    }
}

# ── Helper: remove a path if it exists ──────────────────────
function Remove-IfExists($target) {
    if (Test-Path $target) {
        Remove-Item -Recurse -Force $target
        Write-Removed $target
        $script:RemovedCount++
    }
}

# ── 1. Installed packages ────────────────────────────────────
if ($DoPackages) {
    Write-Header "Installed Packages"
    Remove-IfExists ".venv"
    Remove-IfExists "frontend\node_modules"
    Remove-IfExists "frontend\package-lock.json"
}

# ── 2. Build / cache artifacts ───────────────────────────────
if ($DoCache) {
    Write-Header "Build / Cache Artifacts"
    Remove-IfExists "frontend\.next"
    Remove-IfExists "frontend\tsconfig.tsbuildinfo"
    Remove-IfExists ".pytest_cache"

    Write-Info "Removing Python __pycache__ directories ..."
    Get-ChildItem -Recurse -Directory -Filter "__pycache__" |
        Where-Object { $_.FullName -notmatch "\\.venv\\" -and $_.FullName -notmatch "\\node_modules\\" } |
        Remove-Item -Recurse -Force
    Write-Ok "__pycache__ directories cleared"

    Write-Info "Removing compiled .pyc files ..."
    Get-ChildItem -Recurse -File -Filter "*.pyc" |
        Where-Object { $_.FullName -notmatch "\\.venv\\" -and $_.FullName -notmatch "\\node_modules\\" } |
        Remove-Item -Force
    Write-Ok ".pyc files cleared"

    Get-ChildItem -Recurse -Directory -Filter "*.egg-info" -Depth 3 |
        Where-Object { $_.FullName -notmatch "\\.venv\\" } |
        Remove-Item -Recurse -Force
}

# ── 3. User data ─────────────────────────────────────────────
if ($DoData) {
    Write-Header "User Data"
    Write-Host ""
    Write-Warn "This will permanently delete all uploaded documents,"
    Write-Warn "parsed output, page images, vector indexes, and the registry database."
    Write-Host ""
    $Confirm = Read-Host "  Type 'delete' to confirm"

    if ($Confirm -ne "delete") {
        Write-Info "Data deletion cancelled."
    } else {
        $DataDirs = @(
            "data\raw", "data\parsed", "data\page_images",
            "data\tables", "data\figures", "data\indexes", "data\reports"
        )
        foreach ($dir in $DataDirs) {
            if (Test-Path $dir) {
                Get-ChildItem $dir | Remove-Item -Recurse -Force
                Write-Removed "$dir\*"
                $RemovedCount++
            }
        }
        Remove-IfExists "data\registry.db"
        Remove-IfExists "data\llm_settings.json"
    }
}

# ── Summary ──────────────────────────────────────────────────
Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
if ($RemovedCount -eq 0) {
    Write-Ok "Nothing to remove — workspace already clean."
} else {
    Write-Ok "Done. $RemovedCount item(s) removed."
    if ($DoPackages) {
        Write-Host ""
        Write-Info "Run .\setup.ps1 to reinstall dependencies."
    }
}
Write-Host ""
