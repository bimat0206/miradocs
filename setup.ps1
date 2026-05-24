# ============================================================
# MiraDocs — One-shot Setup Script (Windows PowerShell)
# Usage: .\setup.ps1  (run as Administrator recommended)
#
# What this script does:
#   1. Checks / installs Python 3.11+
#   2. Checks / installs Node.js 20+
#   3. Checks / installs Ollama
#   4. Creates Python virtual environment (.venv)
#   5. Installs Python dependencies (requirements.txt)
#   6. Installs frontend npm dependencies (frontend/)
#   7. Starts Ollama daemon if not running
#   8. Pulls required Ollama models (bge-m3, llama3.2)
#   9. Creates required data directories
#  10. Initialises SQLite registry
#  11. Verifies MCP server is importable
#  12. Prints a final summary
# ============================================================

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# ── Helpers ─────────────────────────────────────────────────
function Write-Ok($msg)     { Write-Host "  ✔  $msg" -ForegroundColor Green }
function Write-Warn($msg)   { Write-Host "  ⚠  $msg" -ForegroundColor Yellow }
function Write-Fail($msg)   { Write-Host "  ✘  $msg" -ForegroundColor Red }
function Write-Info($msg)   { Write-Host "  ℹ  $msg" -ForegroundColor Cyan }
function Write-Header($msg) { Write-Host "`n══ $msg ══" -ForegroundColor Cyan }

$Errors = 0
$Warnings = 0
$Installed = @()
$Skipped = @()

# ── 1. Python 3.11+ ─────────────────────────────────────────
Write-Header "Python"
$PythonBin = $null
foreach ($candidate in @("python3.13", "python3.12", "python3.11", "python")) {
    try {
        $ver = & $candidate --version 2>&1
        if ($ver -match "Python 3\.(1[1-9]|[2-9]\d)") {
            $PythonBin = $candidate
            break
        }
    } catch {}
}

if (-not $PythonBin) {
    Write-Fail "Python 3.11+ not found."
    Write-Host "  Install from https://www.python.org/downloads/ (check 'Add to PATH')" -ForegroundColor Yellow
    Write-Host "  Or: winget install Python.Python.3.12" -ForegroundColor Yellow
    $Errors++
} else {
    $pyVer = & $PythonBin --version 2>&1
    Write-Ok "$pyVer ($PythonBin)"
}

# ── 2. Node.js 20+ ──────────────────────────────────────────
Write-Header "Node.js"
$NodeMajor = 0
try {
    $nodeVer = & node --version 2>&1
    if ($nodeVer -match "^v(\d+)") { $NodeMajor = [int]$Matches[1] }
} catch {}

if ($NodeMajor -lt 20) {
    Write-Fail "Node.js 20+ not found."
    Write-Host "  Install from https://nodejs.org/ or: winget install OpenJS.NodeJS.LTS" -ForegroundColor Yellow
    $Errors++
} else {
    Write-Ok "Node $nodeVer"
    $npmVer = & npm --version 2>&1
    Write-Ok "npm $npmVer"
}

# ── 3. Ollama ────────────────────────────────────────────────
Write-Header "Ollama"
$OllamaFound = $false
try {
    $ollamaVer = & ollama --version 2>&1
    $OllamaFound = $true
    Write-Ok "Ollama $ollamaVer"
} catch {
    Write-Fail "Ollama not found."
    Write-Host "  Install from https://ollama.com/download/windows" -ForegroundColor Yellow
    $Errors++
}

if ($Errors -gt 0) {
    Write-Host ""
    Write-Fail "Missing prerequisites — install the tools above and re-run this script."
    exit 1
}

# ── 4. Python Virtual Environment ───────────────────────────
Write-Header "Python Virtual Environment"
$VenvDir = ".venv"
if (Test-Path "$VenvDir\Scripts\python.exe") {
    Write-Ok ".venv already exists — skipping creation"
    $Skipped += ".venv"
} else {
    Write-Info "Creating virtual environment …"
    & $PythonBin -m venv $VenvDir
    $Installed += ".venv"
    Write-Ok ".venv created"
}

# Activate
& "$VenvDir\Scripts\Activate.ps1"
$activePy = & python --version 2>&1
Write-Ok "Activated: $activePy"

# ── 5. Python Dependencies ───────────────────────────────────
Write-Header "Python Dependencies"
Write-Info "Upgrading pip …"
& python -m pip install -q --upgrade pip

Write-Info "Installing packages from requirements.txt …"
& python -m pip install -q -r requirements.txt
Write-Ok "Python dependencies installed"

# ── 6. Frontend (Next.js) ────────────────────────────────────
Write-Header "Frontend Dependencies (Next.js)"
if (-not (Test-Path "frontend\node_modules")) {
    Write-Info "Installing npm packages in frontend/ …"
    Push-Location frontend
    & npm install --prefer-offline 2>&1 | Select-Object -Last 5
    Pop-Location
    $Installed += "frontend/node_modules"
    Write-Ok "Frontend npm packages installed"
} else {
    Write-Ok "node_modules already present — skipping"
    $Skipped += "frontend/node_modules"
}

# ── 7. Start Ollama Daemon ───────────────────────────────────
Write-Header "Ollama Daemon"
$OllamaUrl = "http://localhost:11434"

function Test-OllamaRunning {
    try {
        $null = Invoke-RestMethod -Uri "$OllamaUrl/api/tags" -TimeoutSec 3 -ErrorAction Stop
        return $true
    } catch { return $false }
}

if (Test-OllamaRunning) {
    Write-Ok "Ollama daemon already running at $OllamaUrl"
} else {
    Write-Info "Starting Ollama daemon in background …"
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
    $wait = 0
    while (-not (Test-OllamaRunning) -and $wait -lt 20) {
        Start-Sleep -Seconds 1
        $wait++
    }
    if (Test-OllamaRunning) {
        Write-Ok "Ollama daemon started"
        $Installed += "ollama-daemon"
    } else {
        Write-Warn "Ollama daemon did not respond within 20 s — model pull may fail"
        $Warnings++
    }
}

# ── 8. Pull Required Ollama Models ───────────────────────────
Write-Header "Ollama Models"
$Models = @("bge-m3", "llama3.2")

foreach ($model in $Models) {
    if (Test-OllamaRunning) {
        try {
            $tags = Invoke-RestMethod -Uri "$OllamaUrl/api/tags" -TimeoutSec 5
            $found = $tags.models | Where-Object { $_.name -like "$model*" }
            if ($found) {
                Write-Ok "Model $model already present"
                $Skipped += "model:$model"
            } else {
                Write-Info "Pulling $model — this may take several minutes …"
                & ollama pull $model
                if ($LASTEXITCODE -eq 0) {
                    Write-Ok "Model $model pulled successfully"
                    $Installed += "model:$model"
                } else {
                    Write-Warn "Failed to pull $model — run manually: ollama pull $model"
                    $Warnings++
                }
            }
        } catch {
            Write-Warn "Could not check models — run manually: ollama pull $model"
            $Warnings++
        }
    } else {
        Write-Warn "Ollama not reachable — skipping pull of $model"
        $Warnings++
    }
}

# ── 9. Data Directories ─────────────────────────────────────
Write-Header "Data Directories"
$DataDirs = @(
    "data\raw",
    "data\parsed",
    "data\page_images",
    "data\tables",
    "data\figures",
    "data\reports",
    "data\indexes\qdrant"
)
foreach ($dir in $DataDirs) {
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
}
Write-Ok "All data directories ready"

# ── 10. SQLite Registry ──────────────────────────────────────
Write-Header "SQLite Registry"
try {
    & python -c "import sqlite3; c=sqlite3.connect('data/registry.db'); c.execute('PRAGMA integrity_check'); c.close()"
    Write-Ok "SQLite registry OK (data/registry.db)"
} catch {
    Write-Warn "SQLite check failed — app will init schema on first start"
    $Warnings++
}

# ── 11. MCP Server Importability ─────────────────────────────
Write-Header "MCP Server"
& python -c "import src.mcp.server" 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Ok "src.mcp.server importable"
} else {
    Write-Warn "src.mcp.server failed to import — check src/mcp/server.py"
    $Warnings++
}

# ── 12. Summary ──────────────────────────────────────────────
Write-Host ""
Write-Host "══════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Setup Summary" -ForegroundColor White
Write-Host "══════════════════════════════════════════" -ForegroundColor Cyan

if ($Installed.Count -gt 0) {
    Write-Host "  Installed:" -ForegroundColor Green
    foreach ($item in $Installed) { Write-Host "    + $item" -ForegroundColor Green }
}
if ($Skipped.Count -gt 0) {
    Write-Host "  Skipped (already present):" -ForegroundColor Cyan
    foreach ($item in $Skipped) { Write-Host "    ○ $item" -ForegroundColor Cyan }
}

Write-Host ""
if ($Warnings -gt 0) {
    Write-Warn "Setup finished with $Warnings warning(s)"
    Write-Host "  Review warnings above — the app may start with reduced functionality." -ForegroundColor Yellow
} else {
    Write-Ok "Setup complete — all checks passed"
}

Write-Host ""
Write-Host "  Next step:" -ForegroundColor White
Write-Host "    .\start.sh   — launch FastAPI + Next.js (use Git Bash or WSL)" -ForegroundColor Cyan
Write-Host ""
Write-Host "  URLs (after start):" -ForegroundColor White
Write-Host "    UI  : http://localhost:3000" -ForegroundColor Cyan
Write-Host "    API : http://localhost:8000" -ForegroundColor Cyan
Write-Host "    Docs: http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host ""
