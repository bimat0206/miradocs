#!/usr/bin/env bash
# ============================================================
# MiraDocs — One-shot Setup Script (macOS)
# Usage: bash setup.sh
#
# What this script does:
#   1. Checks / installs Homebrew
#   2. Checks / installs Python 3.11+
#   3. Checks / installs Node.js 20+
#   4. Checks / installs Ollama
#   5. Creates Python virtual environment (.venv)
#   6. Installs Python dependencies (requirements.txt)
#   7. Installs frontend npm dependencies (frontend/)
#   8. Starts Ollama daemon if not running
#   9. Pulls required Ollama models (bge-m3, qwen2.5:3b)
#  10. Creates required data directories
#  11. Initialises SQLite registry
#  12. Verifies MCP server is importable
#  13. Prints a final summary
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Colour helpers ──────────────────────────────────────────
RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
CYAN=$'\033[0;36m'
BOLD=$'\033[1m'
RESET=$'\033[0m'

ok()     { echo "${GREEN}  ✔  ${1}${RESET}"; }
warn()   { echo "${YELLOW}  ⚠  ${1}${RESET}"; }
fail()   { echo "${RED}  ✘  ${1}${RESET}"; }
info()   { echo "${CYAN}  ℹ  ${1}${RESET}"; }
header() { echo; echo "${BOLD}${CYAN}══ ${1} ══${RESET}"; }

ERRORS=0
WARNINGS=0
SKIPPED=()
INSTALLED=()

# ── 1. Homebrew ─────────────────────────────────────────────
header "Homebrew"
if command -v brew >/dev/null 2>&1; then
    ok "Homebrew $(brew --version | head -1)"
else
    info "Installing Homebrew …"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Reload PATH for Apple Silicon
    if [[ -f /opt/homebrew/bin/brew ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
    INSTALLED+=("homebrew")
    ok "Homebrew installed"
fi

# ── 2. Python 3.11+ ─────────────────────────────────────────
header "Python"
PYTHON_BIN=""
for candidate in python3.13 python3.12 python3.11; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PYTHON_BIN="$candidate"
        break
    fi
done

if [[ -z "$PYTHON_BIN" ]]; then
    info "Python 3.11+ not found — installing via Homebrew …"
    brew install python@3.11
    PYTHON_BIN="python3.11"
    INSTALLED+=("python@3.11")
fi

PYTHON_VERSION="$($PYTHON_BIN --version 2>&1)"
ok "$PYTHON_VERSION (${PYTHON_BIN})"

# ── 3. Node.js 20+ ──────────────────────────────────────────
header "Node.js"
NODE_MAJOR=0
if command -v node >/dev/null 2>&1; then
    NODE_MAJOR=$(node -e "process.stdout.write(String(process.version.match(/^v(\d+)/)[1]))")
fi

if [[ "$NODE_MAJOR" -lt 20 ]]; then
    info "Node.js 20+ not found — installing via Homebrew …"
    brew install node@20
    # Add brew node to PATH
    BREW_NODE_PREFIX="$(brew --prefix node@20)"
    export PATH="${BREW_NODE_PREFIX}/bin:${PATH}"
    INSTALLED+=("node@20")
else
    ok "Node $(node --version)"
fi
ok "npm $(npm --version)"

# ── 4. Ollama ────────────────────────────────────────────────
header "Ollama"
if command -v ollama >/dev/null 2>&1; then
    ok "Ollama $(ollama --version 2>/dev/null || echo 'installed')"
    SKIPPED+=("ollama (already present)")
else
    info "Installing Ollama …"
    brew install --cask ollama 2>/dev/null || {
        # Fallback: official install script
        info "Homebrew cask failed — trying official install script …"
        curl -fsSL https://ollama.com/install.sh | sh
    }
    INSTALLED+=("ollama")
    ok "Ollama installed"
fi

# ── 5. Python Virtual Environment ───────────────────────────
header "Python Virtual Environment"
VENV_DIR=".venv"
if [[ -d "$VENV_DIR" ]]; then
    ok ".venv already exists — skipping creation"
    SKIPPED+=(".venv")
else
    info "Creating virtual environment …"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
    INSTALLED+=(".venv")
    ok ".venv created"
fi

# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"
ok "Activated: $(python --version)"

# ── 6. Python Dependencies ───────────────────────────────────
header "Python Dependencies"
info "Upgrading pip …"
pip install -q --upgrade pip

info "Installing packages from requirements.txt …"
pip install -q -r requirements.txt
ok "Python dependencies installed"

# Verify critical imports
CRITICAL_IMPORTS=(
    "fastapi:fastapi"
    "uvicorn:uvicorn"
    "qdrant_client:qdrant_client"
    "PyMuPDF:fitz"
    "pydantic:pydantic"
    "yaml:yaml"
    "docling:docling"
    "httpx:httpx"
    "pandas:pandas"
    "PIL:PIL"
)

echo
info "Verifying critical imports …"
IMPORT_FAILURES=()
for entry in "${CRITICAL_IMPORTS[@]}"; do
    pkg="${entry%%:*}"
    module="${entry##*:}"
    if python -c "import ${module}" 2>/dev/null; then
        ok "$pkg"
    else
        warn "$pkg — import failed (${module})"
        IMPORT_FAILURES+=("$pkg")
        (( WARNINGS++ )) || true
    fi
done

if [[ ${#IMPORT_FAILURES[@]} -gt 0 ]]; then
    warn "Some imports failed. Re-running pip install …"
    pip install -q -r requirements.txt
fi

# ── 7. Frontend (Next.js) ────────────────────────────────────
header "Frontend Dependencies (Next.js)"
FRONTEND_DIR="frontend"
if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    info "Installing npm packages in ${FRONTEND_DIR}/ …"
    (cd "$FRONTEND_DIR" && npm install --prefer-offline 2>&1 | tail -5)
    INSTALLED+=("frontend/node_modules")
    ok "Frontend npm packages installed"
else
    ok "node_modules already present — skipping"
    SKIPPED+=("frontend/node_modules")
fi

# ── 8. Start Ollama Daemon ───────────────────────────────────
header "Ollama Daemon"
OLLAMA_URL="http://localhost:11434"

ollama_running() {
    curl -sf --max-time 3 "${OLLAMA_URL}/api/tags" -o /dev/null 2>/dev/null
}

if ollama_running; then
    ok "Ollama daemon already running at ${OLLAMA_URL}"
else
    info "Starting Ollama daemon in background …"
    nohup ollama serve >/tmp/ollama-setup.log 2>&1 &
    OLLAMA_PID=$!
    echo "${OLLAMA_PID}" > /tmp/ollama-setup.pid

    # Wait up to 20 s for Ollama to start
    WAIT=0
    until ollama_running || [[ $WAIT -ge 20 ]]; do
        sleep 1
        (( WAIT++ )) || true
    done

    if ollama_running; then
        ok "Ollama daemon started (PID ${OLLAMA_PID})"
        INSTALLED+=("ollama-daemon")
    else
        warn "Ollama daemon did not respond within 20 s — model pull may fail"
        warn "  Check: tail -f /tmp/ollama-setup.log"
        (( WARNINGS++ )) || true
    fi
fi

# ── 9. Pull Required Ollama Models ───────────────────────────
header "Ollama Models"

# Models required by config/settings.yaml
MODELS=(
    "bge-m3"     # Embedding model (1024-dim, dense search)
    "qwen2.5:3b"   # LLM: entity extraction + reranking
)

for model in "${MODELS[@]}"; do
    if ollama_running; then
        if curl -sf --max-time 5 "${OLLAMA_URL}/api/tags" 2>/dev/null | grep -q "\"${model}\""; then
            ok "Model ${model} already present"
            SKIPPED+=("model:${model}")
        else
            info "Pulling ${model} — this may take several minutes …"
            if ollama pull "$model"; then
                ok "Model ${model} pulled successfully"
                INSTALLED+=("model:${model}")
            else
                warn "Failed to pull ${model} — run manually: ollama pull ${model}"
                (( WARNINGS++ )) || true
            fi
        fi
    else
        warn "Ollama not reachable — skipping pull of ${model}"
        warn "  Run manually: ollama pull ${model}"
        (( WARNINGS++ )) || true
    fi
done

# ── 10. Data Directories ─────────────────────────────────────
header "Data Directories"
DATA_DIRS=(
    data/raw
    data/parsed
    data/page_images
    data/tables
    data/figures
    data/reports
    data/indexes/qdrant
)
for dir in "${DATA_DIRS[@]}"; do
    mkdir -p "$dir"
done
ok "All data directories ready"

# ── 11. SQLite Registry ──────────────────────────────────────
header "SQLite Registry"
SQLITE_DB="data/registry.db"
mkdir -p "$(dirname "$SQLITE_DB")"
if python - <<'PYEOF' >/dev/null 2>&1; then
import sqlite3
con = sqlite3.connect("data/registry.db")
con.execute("PRAGMA integrity_check").fetchone()
con.close()
PYEOF
    ok "SQLite registry OK (${SQLITE_DB})"
else
    warn "SQLite check failed — app will init schema on first start"
    (( WARNINGS++ )) || true
fi

# ── 12. MCP Server Importability ─────────────────────────────
header "MCP Server"
if python -c "import src.mcp.server" 2>/dev/null; then
    ok "src.mcp.server importable"
else
    warn "src.mcp.server failed to import — check src/mcp/server.py"
    (( WARNINGS++ )) || true
fi

# ── 13. Summary ──────────────────────────────────────────────
echo
echo "${BOLD}${CYAN}══════════════════════════════════════════${RESET}"
echo "${BOLD}  Setup Summary${RESET}"
echo "${BOLD}${CYAN}══════════════════════════════════════════${RESET}"

if [[ ${#INSTALLED[@]} -gt 0 ]]; then
    echo "${GREEN}  Installed:${RESET}"
    for item in "${INSTALLED[@]}"; do
        echo "    ${GREEN}+${RESET} ${item}"
    done
fi

if [[ ${#SKIPPED[@]} -gt 0 ]]; then
    echo "${CYAN}  Skipped (already present):${RESET}"
    for item in "${SKIPPED[@]}"; do
        echo "    ${CYAN}○${RESET} ${item}"
    done
fi

echo
if [[ $ERRORS -gt 0 ]]; then
    fail "Setup finished with ${ERRORS} error(s) and ${WARNINGS} warning(s)"
    echo "${RED}  Resolve errors above before running ./start.sh${RESET}"
    exit 1
elif [[ $WARNINGS -gt 0 ]]; then
    warn "Setup finished with ${WARNINGS} warning(s)"
    echo "${YELLOW}  Review warnings above — the app may start with reduced functionality.${RESET}"
else
    ok "Setup complete — all checks passed"
fi

echo
echo "${BOLD}  Next step:${RESET}"
echo "    ${CYAN}./start.sh${RESET}   — launch FastAPI + Next.js workspace"
echo
echo "${BOLD}  URLs (after ./start.sh):${RESET}"
echo "    UI  : http://localhost:3000"
echo "    API : http://localhost:8000"
echo "    Docs: http://localhost:8000/docs"
echo
