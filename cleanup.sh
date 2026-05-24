#!/usr/bin/env bash
# ============================================================
# MiraDocs — Cleanup Script (macOS / Linux / WSL)
# Usage:
#   ./cleanup.sh              — interactive menu
#   ./cleanup.sh --packages   — remove .venv + node_modules only
#   ./cleanup.sh --cache      — remove build/cache artifacts only
#   ./cleanup.sh --all        — packages + cache (not data)
#   ./cleanup.sh --data       — delete all user document data
#   ./cleanup.sh --full       — everything (packages + cache + data)
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
info()   { echo "${CYAN}  ℹ  ${1}${RESET}"; }
header() { echo; echo "${BOLD}${CYAN}══ ${1} ══${RESET}"; }
removed() { echo "${RED}  ✘  Removed: ${1}${RESET}"; }

# ── Flags ───────────────────────────────────────────────────
DO_PACKAGES=false
DO_CACHE=false
DO_DATA=false
INTERACTIVE=true

for arg in "$@"; do
    case "$arg" in
        --packages) DO_PACKAGES=true; INTERACTIVE=false ;;
        --cache)    DO_CACHE=true;    INTERACTIVE=false ;;
        --all)      DO_PACKAGES=true; DO_CACHE=true; INTERACTIVE=false ;;
        --data)     DO_DATA=true;     INTERACTIVE=false ;;
        --full)     DO_PACKAGES=true; DO_CACHE=true; DO_DATA=true; INTERACTIVE=false ;;
        --help|-h)
            sed -n '3,9p' "$0" | sed 's/^# \?//'
            exit 0 ;;
        *)
            echo "${RED}Unknown option: ${arg}${RESET}"
            exit 1 ;;
    esac
done

# ── Interactive menu ─────────────────────────────────────────
if [[ "$INTERACTIVE" == true ]]; then
    echo
    echo "${BOLD}${CYAN}  MiraDocs — Cleanup${RESET}"
    echo "  What would you like to remove?"
    echo
    echo "  ${BOLD}1)${RESET} Installed packages      (.venv, frontend/node_modules)"
    echo "  ${BOLD}2)${RESET} Build / cache artifacts  (.next, __pycache__, .pytest_cache, tsconfig.tsbuildinfo)"
    echo "  ${BOLD}3)${RESET} Both 1 + 2               (full reset — re-run setup.sh to restore)"
    echo "  ${BOLD}4)${RESET} User data                (documents, parsed output, registry.db)"
    echo "  ${BOLD}5)${RESET} Everything               (1 + 2 + 4)"
    echo "  ${BOLD}q)${RESET} Quit"
    echo
    printf "  Choice [1-5 / q]: "
    read -r CHOICE

    case "$CHOICE" in
        1) DO_PACKAGES=true ;;
        2) DO_CACHE=true ;;
        3) DO_PACKAGES=true; DO_CACHE=true ;;
        4) DO_DATA=true ;;
        5) DO_PACKAGES=true; DO_CACHE=true; DO_DATA=true ;;
        q|Q) echo; info "Nothing removed."; exit 0 ;;
        *) echo "${RED}  Invalid choice.${RESET}"; exit 1 ;;
    esac
fi

REMOVED_COUNT=0

# ── Helper: remove a path if it exists ──────────────────────
remove() {
    local target="$1"
    if [[ -e "$target" || -L "$target" ]]; then
        rm -rf "$target"
        removed "$target"
        (( REMOVED_COUNT++ )) || true
    fi
}

# ── 1. Installed packages ────────────────────────────────────
if [[ "$DO_PACKAGES" == true ]]; then
    header "Installed Packages"
    remove ".venv"
    remove "frontend/node_modules"
    remove "frontend/package-lock.json"
fi

# ── 2. Build / cache artifacts ───────────────────────────────
if [[ "$DO_CACHE" == true ]]; then
    header "Build / Cache Artifacts"
    remove "frontend/.next"
    remove "frontend/tsconfig.tsbuildinfo"

    # Python caches — walk the tree
    info "Removing Python __pycache__ directories …"
    find . \
        -not -path './.venv/*' \
        -not -path './frontend/node_modules/*' \
        -type d -name '__pycache__' \
        -exec rm -rf {} + 2>/dev/null || true
    ok "__pycache__ directories cleared"

    info "Removing compiled .pyc files …"
    find . \
        -not -path './.venv/*' \
        -not -path './frontend/node_modules/*' \
        -name '*.pyc' -delete 2>/dev/null || true
    ok ".pyc files cleared"

    remove ".pytest_cache"

    # egg-info dirs
    find . \
        -not -path './.venv/*' \
        -maxdepth 3 -type d -name '*.egg-info' \
        -exec rm -rf {} + 2>/dev/null || true
fi

# ── 3. User data ─────────────────────────────────────────────
if [[ "$DO_DATA" == true ]]; then
    header "User Data"
    echo
    warn "This will permanently delete all uploaded documents,"
    warn "parsed output, page images, vector indexes, and the registry database."
    echo
    printf "  ${BOLD}Type 'delete' to confirm: ${RESET}"
    read -r CONFIRM

    if [[ "$CONFIRM" != "delete" ]]; then
        info "Data deletion cancelled."
    else
        DATA_DIRS=(
            data/raw
            data/parsed
            data/page_images
            data/tables
            data/figures
            data/indexes
            data/reports
        )
        for dir in "${DATA_DIRS[@]}"; do
            if [[ -d "$dir" ]]; then
                find "$dir" -mindepth 1 -delete 2>/dev/null || true
                removed "${dir}/*"
                (( REMOVED_COUNT++ )) || true
            fi
        done

        remove "data/registry.db"
        remove "data/llm_settings.json"
    fi
fi

# ── Summary ──────────────────────────────────────────────────
echo
echo "${BOLD}${CYAN}══════════════════════════════════════════${RESET}"
if [[ $REMOVED_COUNT -eq 0 ]]; then
    ok "Nothing to remove — workspace already clean."
else
    ok "Done. ${REMOVED_COUNT} item(s) removed."
    if [[ "$DO_PACKAGES" == true ]]; then
        echo
        info "Run ${BOLD}./setup.sh${RESET}${CYAN} to reinstall dependencies."
    fi
fi
echo
