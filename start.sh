#!/usr/bin/env bash
# ============================================================
# MiraDocs — FastAPI + Next.js + MCP launcher
# Usage: bash start.sh  (or ./start.sh after chmod +x)
#
# Services managed:
#   API  : FastAPI/uvicorn on :${API_PORT}
#   UI   : Next.js dev server on :${WEB_PORT}
#   MCP  : stdio server (spawned on-demand by MCP clients)
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv"
API_PORT=8000
WEB_PORT=3000
OLLAMA_URL="http://localhost:11434"
SQLITE_DB="data/registry.db"
QDRANT_DATA_DIR="data/indexes/qdrant"
FRONTEND_DIR="frontend"
MCP_MODULE="src.mcp.server"   # stdio transport — NOT backgrounded; spawned per-connection by MCP client

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
CYAN=$'\033[0;36m'
BOLD=$'\033[1m'
RESET=$'\033[0m'

ok()   { echo "${GREEN}  ✔  ${1}${RESET}"; }
warn() { echo "${YELLOW}  ⚠  ${1}${RESET}"; }
fail() { echo "${RED}  ✘  ${1}${RESET}"; }
info() { echo "${CYAN}  ℹ  ${1}${RESET}"; }
header() { echo; echo "${BOLD}${CYAN}══ ${1} ══${RESET}"; }

API_PID=""
WEB_PID=""
ERRORS=0
WARNINGS=0

github_repo_from_origin() {
    local url repo
    if ! url=$(git remote get-url origin 2>/dev/null); then
        return 1
    fi

    case "$url" in
        git@github.com:*) repo="${url#git@github.com:}" ;;
        *github.com/*) repo="${url#*github.com/}" ;;
        *) return 1 ;;
    esac

    repo="${repo%.git}"
    if [[ -z "$repo" || "$repo" == "$url" ]]; then
        return 1
    fi
    echo "$repo"
}

remote_main_version() {
    local repo="$1"
    local url="https://raw.githubusercontent.com/${repo}/main/VERSION"
    if ! command -v curl >/dev/null 2>&1; then
        return 1
    fi
    curl -fsSL --max-time 5 "$url" 2>/dev/null | tr -d '[:space:]'
}

check_startup_update() {
    if [[ "${MIRADOCS_SKIP_START_UPDATE:-}" == "1" ]]; then
        return 0
    fi
    if [[ ! -f VERSION ]]; then
        return 0
    fi

    local local_version repo remote_version
    local_version="$(tr -d '[:space:]' < VERSION)"
    if [[ -z "$local_version" ]]; then
        return 0
    fi

    if ! repo="$(github_repo_from_origin)"; then
        return 0
    fi
    if ! remote_version="$(remote_main_version "$repo")"; then
        return 0
    fi
    if [[ -z "$remote_version" || "$remote_version" == "$local_version" ]]; then
        return 0
    fi

    header "Startup Update"
    info "Update available: ${local_version} -> ${remote_version}"
    info "Running update.sh before launching MiraDocs"
    if [[ ! -f update.sh ]]; then
        warn "update.sh not found; continuing normal startup"
        return 0
    fi

    MIRADOCS_SKIP_START_UPDATE=1 bash update.sh
    exit 0
}

check_startup_update
if [[ "${MIRADOCS_START_UPDATE_ONLY:-}" == "1" ]]; then
    exit 0
fi

cleanup() {
    echo
    info "Shutting down MiraDocs …"

    # 1. Graceful SIGTERM to tracked PIDs
    for pid in "$WEB_PID" "$API_PID"; do
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill -TERM "$pid" 2>/dev/null || true
        fi
    done
    sleep 1

    # 2. Force-kill if still alive
    for pid in "$WEB_PID" "$API_PID"; do
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill -KILL "$pid" 2>/dev/null || true
        fi
    done

    # 3. Sweep ports — catches orphan Next.js workers or uvicorn children
    for port in "$API_PORT" "$WEB_PORT"; do
        local port_pids
        port_pids=$(lsof -iTCP:"${port}" -sTCP:LISTEN -t 2>/dev/null || true)
        if [[ -n "$port_pids" ]]; then
            warn "Force-releasing port ${port} (PIDs: ${port_pids})"
            # shellcheck disable=SC2086
            kill -KILL $port_pids 2>/dev/null || true
        fi
    done

    ok "All ports released — goodbye!"
}

trap cleanup INT TERM EXIT

header "Environment"
if [[ ! -d "$VENV_DIR" ]]; then
    warn "No .venv found — creating one now"
    python3 -m venv "$VENV_DIR"
fi

# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"
ok "Python $(python --version)"

if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
    fail "Node.js and npm are required for the Next.js UI"
    exit 1
fi
ok "Node $(node --version)"
ok "npm $(npm --version)"

header "Python Dependencies"
MISSING_PKGS=()
for pkg in fastapi uvicorn qdrant_client PyMuPDF pydantic yaml; do
    module="$pkg"
    case "$pkg" in
        PyMuPDF) module="fitz" ;;
        yaml) module="yaml" ;;
        qdrant_client) module="qdrant_client" ;;
    esac
    if python -c "import ${module}" 2>/dev/null; then
        ok "$pkg"
    else
        warn "$pkg not installed"
        MISSING_PKGS+=("$pkg")
    fi
done

if [[ ${#MISSING_PKGS[@]} -gt 0 ]]; then
    info "Installing Python dependencies from requirements.txt …"
    pip install -q -r requirements.txt
    ok "Python dependencies installed"
fi

header "Frontend Dependencies"
if [[ ! -d "${FRONTEND_DIR}/node_modules" ]]; then
    info "Installing frontend packages …"
    (cd "$FRONTEND_DIR" && npm install)
else
    ok "Frontend node_modules found"
fi

header "Local Services"
if curl -sf --max-time 3 "${OLLAMA_URL}/api/tags" -o /dev/null 2>/dev/null; then
    ok "Ollama reachable at ${OLLAMA_URL}"
    if curl -sf --max-time 3 "${OLLAMA_URL}/api/tags" 2>/dev/null | grep -q "bge-m3"; then
        ok "Model bge-m3 is available"
    else
        warn "Model bge-m3 not found — run: ollama pull bge-m3"
        (( WARNINGS++ )) || true
    fi
else
    warn "Ollama not responding; indexing/search embeddings will be degraded"
    (( WARNINGS++ )) || true
fi

mkdir -p "$QDRANT_DATA_DIR"
ok "Qdrant path ready: $QDRANT_DATA_DIR"

mkdir -p "$(dirname "$SQLITE_DB")"
if python - <<'PYEOF' >/dev/null 2>&1; then
import sqlite3
con = sqlite3.connect("data/registry.db")
con.execute("PRAGMA integrity_check").fetchone()
con.close()
PYEOF
    ok "SQLite registry OK: $SQLITE_DB"
else
    warn "SQLite registry check failed; app will initialize schema on startup"
    (( WARNINGS++ )) || true
fi

for dir in data/raw data/parsed data/page_images data/tables data/figures data/reports data/indexes; do
    mkdir -p "$dir"
done
ok "Data directories ready"

header "Port Check"

free_port() {
    local port="$1"
    local pids
    pids=$(lsof -iTCP:"${port}" -sTCP:LISTEN -t 2>/dev/null || true)
    if [[ -z "$pids" ]]; then
        ok "Port ${port} is free"
        return 0
    fi

    warn "Port ${port} in use (PID(s): ${pids}) — killing …"

    # Graceful SIGTERM first
    # shellcheck disable=SC2086
    kill -TERM $pids 2>/dev/null || true
    sleep 1

    # Check survivors; escalate to SIGKILL
    local survivors
    survivors=$(lsof -iTCP:"${port}" -sTCP:LISTEN -t 2>/dev/null || true)
    if [[ -n "$survivors" ]]; then
        # shellcheck disable=SC2086
        kill -KILL $survivors 2>/dev/null || true
        sleep 1
    fi

    # Final check
    if lsof -iTCP:"${port}" -sTCP:LISTEN -t >/dev/null 2>&1; then
        fail "Could not free port ${port} — please release it manually and retry"
        (( ERRORS++ )) || true
    else
        ok "Port ${port} freed"
    fi
}

for port in "$API_PORT" "$WEB_PORT"; do
    free_port "$port"
done

header "MCP Server (stdio transport)"
# The MCP server uses JSON-RPC over stdio — it is NOT a daemon.
# MCP clients (Claude Code, Cursor, etc.) spawn it per-connection.
# We only verify it can be imported here.
PYTHON_BIN="$(python -c 'import sys; print(sys.executable)')"
if python -c "import src.mcp.server" 2>/dev/null; then
    ok "MCP server module importable (src.mcp.server)"
else
    fail "MCP server module failed to import — check src/mcp/server.py and its dependencies"
    (( ERRORS++ )) || true
fi


echo
echo "${BOLD}══════════════════════════════════════════${RESET}"
if [[ $ERRORS -gt 0 ]]; then
    fail "Health check: $ERRORS error(s), $WARNINGS warning(s)"
    echo "${RED}Cannot start — free the occupied ports or adjust start.sh.${RESET}"
    exit 1
elif [[ $WARNINGS -gt 0 ]]; then
    warn "Health check: 0 errors, $WARNINGS warning(s)"
    echo "${YELLOW}Starting with degraded optional functionality …${RESET}"
else
    ok "All checks passed"
fi
echo "${BOLD}══════════════════════════════════════════${RESET}"
echo

header "Launch"
info "Starting API on http://localhost:${API_PORT}"
uvicorn src.api.main:app --host 0.0.0.0 --port "$API_PORT" &
API_PID=$!

info "Starting UI on http://localhost:${WEB_PORT}"
(cd "$FRONTEND_DIR" && NEXT_PUBLIC_API_URL="http://localhost:${API_PORT}" npm run dev) &
WEB_PID=$!

(
    sleep 3
    if command -v open >/dev/null 2>&1; then
        open "http://localhost:${WEB_PORT}"
    elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "http://localhost:${WEB_PORT}"
    fi
) &

info "Press Ctrl+C to stop both services"

# Monitor: if either process exits unexpectedly, shut everything down
while true; do
    if [[ -n "$API_PID" ]] && ! kill -0 "$API_PID" 2>/dev/null; then
        fail "FastAPI process exited unexpectedly (PID $API_PID)"
        cleanup
        exit 1
    fi
    if [[ -n "$WEB_PID" ]] && ! kill -0 "$WEB_PID" 2>/dev/null; then
        fail "Next.js process exited unexpectedly (PID $WEB_PID)"
        cleanup
        exit 1
    fi
    sleep 2
done
