#!/usr/bin/env python3
"""MiraDocs — One-shot Setup Script (cross-platform).

Usage: python3 setup.py

What this script does:
  1. Checks / installs Python 3.11+ (guidance only on non-macOS)
  2. Checks / installs Node.js 20+ (guidance only on non-macOS)
  3. Checks / installs Ollama
  4. Creates Python virtual environment (.venv)
  5. Installs Python dependencies (requirements.txt)
  6. Installs frontend npm dependencies (frontend/)
  7. Starts Ollama daemon if not running
  8. Pulls required Ollama models (read from config/settings.yaml)
  9. Creates required data directories
 10. Initialises SQLite registry
 11. Verifies MCP server is importable
 12. Prints a final summary
"""
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

# ── Colour helpers ───────────────────────────────────────────────────────────
_USE_COLOR = sys.stdout.isatty() and (os.name != "nt" or os.environ.get("WT_SESSION"))

def _c(code: str, msg: str) -> str:
    return f"\033[{code}m{msg}\033[0m" if _USE_COLOR else msg

def ok(msg):      print(_c("32", f"  ✔  {msg}"))
def warn(msg):    print(_c("33", f"  ⚠  {msg}"))
def fail(msg):    print(_c("31", f"  ✘  {msg}"))
def info(msg):    print(_c("36", f"  ℹ  {msg}"))
def header(msg):  print(_c("1;36", f"\n══ {msg} ══"))

errors = 0
warnings = 0
installed: list[str] = []
skipped: list[str] = []

def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)

def has_cmd(name: str) -> bool:
    return shutil.which(name) is not None

def brew_install(pkg: str):
    subprocess.run(["brew", "install", pkg], check=True)

# ── 1. Homebrew (macOS only) ─────────────────────────────────────────────────
IS_MAC = platform.system() == "Darwin"

if IS_MAC:
    header("Homebrew")
    if has_cmd("brew"):
        ok(f"Homebrew found")
    else:
        info("Installing Homebrew …")
        subprocess.run(
            ["/bin/bash", "-c", "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"],
            check=True,
        )
        # Reload PATH for Apple Silicon
        brew_path = Path("/opt/homebrew/bin/brew")
        if brew_path.exists():
            os.environ["PATH"] = f"/opt/homebrew/bin:{os.environ['PATH']}"
        installed.append("homebrew")
        ok("Homebrew installed")

# ── 2. Python 3.11+ ─────────────────────────────────────────────────────────
header("Python")
python_bin = None
for candidate in ("python3.13", "python3.12", "python3.11", "python3"):
    path = shutil.which(candidate)
    if path:
        r = run([path, "--version"])
        if r.returncode == 0:
            ver = r.stdout.strip().split()[-1]
            major, minor = (int(x) for x in ver.split(".")[:2])
            if major >= 3 and minor >= 11:
                python_bin = path
                break

if not python_bin:
    if IS_MAC:
        info("Python 3.11+ not found — installing via Homebrew …")
        brew_install("python@3.12")
        python_bin = shutil.which("python3.12") or shutil.which("python3")
        installed.append("python@3.12")
    else:
        fail("Python 3.11+ not found. Install it from https://python.org/downloads/")
        sys.exit(1)

ok(f"{run([python_bin, '--version']).stdout.strip()} ({python_bin})")

# ── 3. Node.js 20+ ──────────────────────────────────────────────────────────
header("Node.js")
node_ok = False
if has_cmd("node"):
    r = run(["node", "-e", "process.stdout.write(String(process.versions.node))"])
    if r.returncode == 0:
        node_major = int(r.stdout.split(".")[0])
        if node_major >= 20:
            node_ok = True
            ok(f"Node v{r.stdout.strip()}")

if not node_ok:
    if IS_MAC:
        info("Node.js 20+ not found — installing via Homebrew …")
        brew_install("node@20")
        installed.append("node@20")
        ok("Node.js installed")
    else:
        fail("Node.js 20+ not found. Install from https://nodejs.org/")
        sys.exit(1)

# ── 4. Ollama ────────────────────────────────────────────────────────────────
header("Ollama")
if has_cmd("ollama"):
    ok("Ollama found")
    skipped.append("ollama")
else:
    if IS_MAC:
        info("Installing Ollama …")
        try:
            subprocess.run(["brew", "install", "--cask", "ollama"], check=True)
        except subprocess.CalledProcessError:
            info("Homebrew cask failed — trying official install script …")
            subprocess.run(["bash", "-c", "curl -fsSL https://ollama.com/install.sh | sh"], check=True)
        installed.append("ollama")
        ok("Ollama installed")
    elif platform.system() == "Linux":
        info("Installing Ollama via official script …")
        subprocess.run(["bash", "-c", "curl -fsSL https://ollama.com/install.sh | sh"], check=True)
        installed.append("ollama")
        ok("Ollama installed")
    else:
        warn("Ollama not found. Install from https://ollama.com/download")
        warnings += 1

# ── 5. Python Virtual Environment ───────────────────────────────────────────
header("Python Virtual Environment")
venv_dir = ROOT / ".venv"
if venv_dir.is_dir():
    ok(".venv already exists — skipping creation")
    skipped.append(".venv")
else:
    info("Creating virtual environment …")
    subprocess.run([python_bin, "-m", "venv", str(venv_dir)], check=True)
    installed.append(".venv")
    ok(".venv created")

# Determine venv python/pip
if os.name == "nt":
    venv_python = str(venv_dir / "Scripts" / "python.exe")
    venv_pip = str(venv_dir / "Scripts" / "pip.exe")
else:
    venv_python = str(venv_dir / "bin" / "python")
    venv_pip = str(venv_dir / "bin" / "pip")

# ── 6. Python Dependencies ───────────────────────────────────────────────────
header("Python Dependencies")
info("Upgrading pip …")
subprocess.run([venv_pip, "install", "-q", "--upgrade", "pip"], check=True)
info("Installing packages from requirements.txt …")
subprocess.run([venv_pip, "install", "-q", "-r", "requirements.txt"], check=True)
ok("Python dependencies installed")

# Verify critical imports
critical = ["fastapi", "uvicorn", "qdrant_client", "fitz", "pydantic", "yaml", "docling", "httpx"]
info("Verifying critical imports …")
import_failures = []
for mod in critical:
    r = run([venv_python, "-c", f"import {mod}"])
    if r.returncode == 0:
        ok(mod)
    else:
        warn(f"{mod} — import failed")
        import_failures.append(mod)
        warnings += 1

if import_failures:
    warn("Re-running pip install …")
    subprocess.run([venv_pip, "install", "-q", "-r", "requirements.txt"], check=True)

# ── 7. Frontend (Next.js) ────────────────────────────────────────────────────
header("Frontend Dependencies (Next.js)")
frontend = ROOT / "frontend"
if (frontend / "node_modules").is_dir():
    ok("node_modules already present — skipping")
    skipped.append("frontend/node_modules")
else:
    info("Installing npm packages …")
    subprocess.run(["npm", "install", "--prefer-offline"], cwd=str(frontend), check=True)
    installed.append("frontend/node_modules")
    ok("Frontend npm packages installed")

# ── 8. Start Ollama Daemon ───────────────────────────────────────────────────
header("Ollama Daemon")
OLLAMA_URL = "http://localhost:11434"

def ollama_running() -> bool:
    try:
        urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3)
        return True
    except Exception:
        return False

if ollama_running():
    ok(f"Ollama daemon already running at {OLLAMA_URL}")
else:
    if has_cmd("ollama"):
        info("Starting Ollama daemon in background …")
        subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(20):
            time.sleep(1)
            if ollama_running():
                break
        if ollama_running():
            ok("Ollama daemon started")
        else:
            warn("Ollama daemon did not respond within 20 s")
            warnings += 1
    else:
        warn("Ollama not installed — skipping daemon start")
        warnings += 1

# ── 9. Pull Required Ollama Models ───────────────────────────────────────────
header("Ollama Models")
import yaml  # noqa: E402 (available from system python or just-installed venv)

config_path = ROOT / "config" / "settings.yaml"
models: set[str] = set()
if config_path.exists():
    cfg = yaml.safe_load(config_path.read_text())
    for section in cfg.values():
        if isinstance(section, dict):
            for key in ("model", "ollama_model", "rerank_model"):
                if key in section and section[key]:
                    models.add(section[key])

for model in sorted(models):
    if not ollama_running():
        warn(f"Ollama not reachable — skipping pull of {model}")
        warnings += 1
        continue
    # Check if model already present
    try:
        r = urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5)
        import json
        tags = json.loads(r.read())
        names = [m.get("name", "").split(":")[0] for m in tags.get("models", [])]
        if model.split(":")[0] in names:
            ok(f"Model {model} already present")
            skipped.append(f"model:{model}")
            continue
    except Exception:
        pass
    info(f"Pulling {model} — this may take several minutes …")
    result = subprocess.run(["ollama", "pull", model])
    if result.returncode == 0:
        ok(f"Model {model} pulled successfully")
        installed.append(f"model:{model}")
    else:
        warn(f"Failed to pull {model} — run manually: ollama pull {model}")
        warnings += 1

# ── 10. Data Directories ─────────────────────────────────────────────────────
header("Data Directories")
for d in ("raw", "parsed", "page_images", "tables", "figures", "reports", "indexes/qdrant"):
    (ROOT / "data" / d).mkdir(parents=True, exist_ok=True)
ok("All data directories ready")

# ── 11. SQLite Registry ──────────────────────────────────────────────────────
header("SQLite Registry")
db_path = ROOT / "data" / "registry.db"
try:
    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA integrity_check").fetchone()
    con.close()
    ok(f"SQLite registry OK ({db_path.relative_to(ROOT)})")
except Exception:
    warn("SQLite check failed — app will init schema on first start")
    warnings += 1

# ── 12. MCP Server Importability ─────────────────────────────────────────────
header("MCP Server")
r = run([venv_python, "-c", "import src.mcp.server"])
if r.returncode == 0:
    ok("src.mcp.server importable")
else:
    warn("src.mcp.server failed to import")
    warnings += 1

# ── 13. Summary ──────────────────────────────────────────────────────────────
print(_c("1;36", "\n══════════════════════════════════════════"))
print(_c("1", "  Setup Summary"))
print(_c("1;36", "══════════════════════════════════════════"))

if installed:
    print(_c("32", "  Installed:"))
    for item in installed:
        print(f"    {_c('32', '+')} {item}")

if skipped:
    print(_c("36", "  Skipped (already present):"))
    for item in skipped:
        print(f"    {_c('36', '○')} {item}")

print()
if errors > 0:
    fail(f"Setup finished with {errors} error(s) and {warnings} warning(s)")
    sys.exit(1)
elif warnings > 0:
    warn(f"Setup finished with {warnings} warning(s)")
else:
    ok("Setup complete — all checks passed")

print(f"\n{_c('1', '  Next step:')}")
print(f"    {_c('36', 'python3 start.py')}   — launch FastAPI + Next.js workspace")
print(f"\n{_c('1', '  URLs (after start):')}")
print("    UI  : http://localhost:3000")
print("    API : http://localhost:8000")
print("    Docs: http://localhost:8000/docs\n")
