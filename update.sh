#!/usr/bin/env bash
# ============================================================
# MiraDocs — Auto-Update Script
# Runs as a detached process: stops services, pulls updates,
# installs dependencies if changed, then restarts the stack.
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

LOG_FILE="data/update.log"
STATUS_FILE="data/update-status.json"
UPDATE_HANDOFF_FILE="data/update-restart-requested"
VENV_DIR=".venv"
FRONTEND_DIR="frontend"
API_PORT=8000
CURRENT_VERSION=$(cat VERSION 2>/dev/null || echo "unknown")

write_status() {
  local status="$1"
  local message="$2"
  local version="${3:-}"
  cat > "$STATUS_FILE" <<EOF
{"status":"$status","message":"$message","version":"$version","timestamp":"$(date -u +%Y-%m-%dT%H:%M:%SZ)"}
EOF
}

log() {
  echo "[$(date '+%H:%M:%S')] $1" >> "$LOG_FILE"
}

# Ensure data dir exists for log/status files
mkdir -p data
trap 'rm -f "$UPDATE_HANDOFF_FILE"' EXIT

# Clear previous log
> "$LOG_FILE"

write_status "updating" "Starting update..." "$CURRENT_VERSION"
log "=== MiraDocs Update Started ==="

# ── 1. Wait for HTTP response to finish ──
sleep 2

# ── 2. Stop running services ──
log "Stopping services..."
write_status "updating" "Stopping services..." "$CURRENT_VERSION"
printf '%s\n' "$$" > "$UPDATE_HANDOFF_FILE"

# Kill FastAPI (uvicorn) and Next.js processes for this project
pkill -f "uvicorn src.api.main:app" 2>/dev/null || true
pkill -f "next dev.*--port 3000" 2>/dev/null || true
pkill -f "next start.*--port 3000" 2>/dev/null || true
sleep 2

log "Services stopped."

# ── 3. Save current state for rollback ──
PREV_COMMIT=$(git rev-parse HEAD)
PREV_VERSION=$(cat VERSION 2>/dev/null || echo "unknown")
STASHED=false
log "Previous version: $PREV_VERSION ($PREV_COMMIT)"

# ── 4. Pull latest from remote ──
log "Pulling latest changes..."
write_status "updating" "Pulling latest changes..." "$PREV_VERSION"

# Stash any locally modified tracked files so the pull can proceed cleanly.
# Track whether we stashed so we can restore afterward.
if ! git diff --quiet 2>/dev/null; then
  log "Stashing local changes..."
  if git stash >> "$LOG_FILE" 2>&1; then
    STASHED=true
  else
    log "WARNING: git stash failed — continuing anyway"
  fi
fi

if ! git pull --ff-only >> "$LOG_FILE" 2>&1; then
  log "ERROR: git pull failed. Attempting reset..."
  git fetch origin >> "$LOG_FILE" 2>&1
  git reset --hard origin/main >> "$LOG_FILE" 2>&1 || {
    write_status "failed" "Git pull failed. Manual intervention required." "$PREV_VERSION"
    log "FATAL: Could not update from remote."
    exit 1
  }
fi

# Restore stashed changes now that the pull is done
if [[ "$STASHED" == "true" ]]; then
  log "Restoring stashed local changes..."
  git stash pop >> "$LOG_FILE" 2>&1 || log "WARNING: git stash pop failed — stash preserved as stash@{0}"
fi

NEW_VERSION=$(cat VERSION 2>/dev/null || echo "unknown")
log "New version: $NEW_VERSION"

# ── 5. Install dependencies if changed ──
log "Checking dependencies..."
write_status "updating" "Installing dependencies..." "$NEW_VERSION"

# Check if Python deps changed
if ! git diff --quiet "$PREV_COMMIT" HEAD -- requirements.txt 2>/dev/null; then
  log "requirements.txt changed — reinstalling Python deps..."
  "$VENV_DIR/bin/pip" install -r requirements.txt >> "$LOG_FILE" 2>&1
fi

# Check if Node deps changed
if ! git diff --quiet "$PREV_COMMIT" HEAD -- "$FRONTEND_DIR/package.json" 2>/dev/null; then
  log "package.json changed — reinstalling Node deps..."
  (cd "$FRONTEND_DIR" && npm install) >> "$LOG_FILE" 2>&1
fi

# ── 6. Restart the stack ──
log "Restarting services..."
write_status "updating" "Restarting services..." "$NEW_VERSION"

# Start using the same start.sh mechanism without re-entering startup update.
MIRADOCS_SKIP_START_UPDATE=1 bash start.sh >> "$LOG_FILE" 2>&1 &

# Wait for API to become healthy
log "Waiting for API to come up..."
for i in $(seq 1 30); do
  if curl -s "http://localhost:${API_PORT}/api/health" > /dev/null 2>&1; then
    log "API is healthy."
    write_status "success" "Updated to $NEW_VERSION" "$NEW_VERSION"
    rm -f "$UPDATE_HANDOFF_FILE"
    log "=== Update Complete ==="
    exit 0
  fi
  sleep 2
done

# Timeout — services didn't come back
write_status "failed" "Services failed to restart after update." "$NEW_VERSION"
rm -f "$UPDATE_HANDOFF_FILE"
log "ERROR: Services did not become healthy within 60s."
exit 1
