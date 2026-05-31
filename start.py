#!/usr/bin/env python3
"""MiraDocs launcher and updater.

This module owns both startup and update flow. The shell scripts are kept as
thin compatibility wrappers so existing commands still work.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


class Style:
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    CYAN = "\033[0;36m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


class Launcher:
    VENV_DIR = ".venv"
    FRONTEND_DIR = "frontend"
    API_PORT = 8000
    WEB_PORT = 3000
    OLLAMA_URL = "http://localhost:11434"
    SQLITE_DB = Path("data/registry.db")
    QDRANT_DATA_DIR = Path("data/indexes/qdrant")
    MCP_MODULE = "src.mcp.server"
    LOG_FILE = Path("data/update.log")
    STATUS_FILE = Path("data/update-status.json")
    UPDATE_HANDOFF_FILE = Path("data/update-restart-requested")
    UPDATE_HANDOFF_TTL_SECONDS = 300

    def __init__(self, root: Path | None = None, env: dict[str, str] | None = None) -> None:
        self.root = (root or Path(__file__).resolve().parent).resolve()
        self.env = env if env is not None else os.environ
        self.api_proc: subprocess.Popen[bytes] | None = None
        self.web_proc: subprocess.Popen[bytes] | None = None
        self.errors = 0
        self.warnings = 0

    def ok(self, message: str) -> None:
        print(f"{Style.GREEN}  ✔  {message}{Style.RESET}", flush=True)

    def warn(self, message: str) -> None:
        print(f"{Style.YELLOW}  ⚠  {message}{Style.RESET}", flush=True)

    def fail(self, message: str) -> None:
        print(f"{Style.RED}  ✘  {message}{Style.RESET}", flush=True)

    def info(self, message: str) -> None:
        print(f"{Style.CYAN}  ℹ  {message}{Style.RESET}", flush=True)

    def header(self, message: str) -> None:
        print(f"\n{Style.BOLD}{Style.CYAN}══ {message} ══{Style.RESET}", flush=True)

    def run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        stdout=None,
        stderr=None,
        check: bool = False,
        timeout: int | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            args,
            cwd=str(cwd or self.root),
            env=env,
            stdout=stdout,
            stderr=stderr,
            check=check,
            timeout=timeout,
        )

    def run_text(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        timeout: int | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            cwd=str(cwd or self.root),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )

    @property
    def venv_python(self) -> Path:
        return self.root / self.VENV_DIR / "bin" / "python"

    @property
    def venv_pip(self) -> Path:
        return self.root / self.VENV_DIR / "bin" / "pip"

    def local_version(self) -> str:
        try:
            return (self.root / "VERSION").read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return "unknown"

    def github_repo_from_origin(self) -> str | None:
        result = self.run_text(["git", "remote", "get-url", "origin"], timeout=5)
        if result.returncode != 0:
            return None
        url = result.stdout.strip()
        if url.startswith("git@github.com:"):
            repo = url.removeprefix("git@github.com:")
        elif "github.com/" in url:
            repo = url.split("github.com/", 1)[1]
        else:
            return None
        repo = repo.removesuffix(".git")
        return repo or None

    def remote_main_version(self, repo: str) -> str | None:
        url = f"https://raw.githubusercontent.com/{repo}/main/VERSION"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "MiraDocs"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.read().decode().strip()
        except Exception:
            return None

    def check_startup_update(self) -> bool:
        if self.env.get("MIRADOCS_SKIP_START_UPDATE") == "1":
            return False
        version_file = self.root / "VERSION"
        if not version_file.exists():
            return False
        local_version = self.local_version()
        if not local_version or local_version == "unknown":
            return False
        repo = self.github_repo_from_origin()
        if not repo:
            return False

        self.info("Checking for updates …")
        remote_version = self.remote_main_version(repo)
        if not remote_version or remote_version == local_version:
            return False

        self.header("Update Available")
        self.info(f"Current version : {local_version}")
        self.info(f"Latest version  : {remote_version}")
        print(f"\n{Style.BOLD}  Update now? [y/N] {Style.RESET}", end="", flush=True)
        try:
            answer = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = ""

        if answer not in ("y", "yes"):
            self.info("Skipping update — continuing with current version")
            return False

        self.info("Running update …")
        if self.run_update(mode="startup") != 0:
            self.fail("Update failed; see data/update.log for details")
            raise SystemExit(1)
        self.info("Restarting MiraDocs from the updated launcher")
        if self.env.get("MIRADOCS_START_UPDATE_ONLY") == "1":
            return True
        os.execvpe(
            sys.executable,
            [sys.executable, str(self.root / "start.py"), "start", "--skip-start-update"],
            {**os.environ, "MIRADOCS_SKIP_START_UPDATE": "1"},
        )
        return True

    def start(self, *, skip_start_update: bool = False) -> int:
        os.chdir(self.root)
        if skip_start_update:
            self.env["MIRADOCS_SKIP_START_UPDATE"] = "1"
        self.check_startup_update()
        if self.env.get("MIRADOCS_START_UPDATE_ONLY") == "1":
            return 0
        if self.env.get("MIRADOCS_TEST_UPDATE_HANDOFF_EXIT") == "1":
            return self.handle_process_exit("Next.js", 12345)

        self.register_signal_handlers()
        self.check_environment()
        self.check_python_dependencies()
        self.check_frontend_dependencies()
        self.check_local_services()
        self.check_ports()
        self.check_mcp()
        self.print_health_summary()
        if self.errors:
            return 1
        self.launch_services()
        return self.monitor_services()

    def check_environment(self) -> None:
        self.header("Environment")
        venv_dir = self.root / self.VENV_DIR
        if not venv_dir.exists():
            self.warn("No .venv found — creating one now")
            self.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
        py_version = self.run_text([str(self.venv_python), "--version"]).stdout.strip()
        self.ok(f"Python {py_version.removeprefix('Python ')}")

        node = shutil.which("node")
        npm = shutil.which("npm")
        if not node or not npm:
            self.fail("Node.js and npm are required for the Next.js UI")
            self.errors += 1
            return
        self.ok(f"Node {self.run_text([node, '--version']).stdout.strip()}")
        self.ok(f"npm {self.run_text([npm, '--version']).stdout.strip()}")

    def check_python_dependencies(self) -> None:
        self.header("Python Dependencies")
        packages = {
            "fastapi": "fastapi",
            "uvicorn": "uvicorn",
            "qdrant_client": "qdrant_client",
            "PyMuPDF": "fitz",
            "pydantic": "pydantic",
            "yaml": "yaml",
        }
        missing: list[str] = []
        for package, module in packages.items():
            result = self.run([str(self.venv_python), "-c", f"import {module}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if result.returncode == 0:
                self.ok(package)
            else:
                self.warn(f"{package} not installed")
                missing.append(package)
        if missing:
            self.info("Installing Python dependencies from requirements.txt …")
            self.run([str(self.venv_pip), "install", "-q", "-r", "requirements.txt"], check=True)
            self.ok("Python dependencies installed")

    def check_frontend_dependencies(self) -> None:
        self.header("Frontend Dependencies")
        if not (self.root / self.FRONTEND_DIR / "node_modules").exists():
            self.info("Installing frontend packages …")
            self.run(["npm", "install"], cwd=self.root / self.FRONTEND_DIR, check=True)
        else:
            self.ok("Frontend node_modules found")

    def check_local_services(self) -> None:
        self.header("Local Services")
        try:
            with urllib.request.urlopen(f"{self.OLLAMA_URL}/api/tags", timeout=3) as resp:
                body = resp.read().decode(errors="replace")
            self.ok(f"Ollama reachable at {self.OLLAMA_URL}")
            if "bge-m3" in body:
                self.ok("Model bge-m3 is available")
            else:
                self.warn("Model bge-m3 not found — run: ollama pull bge-m3")
                self.warnings += 1
        except Exception:
            self.warn("Ollama not responding; indexing/search embeddings will be degraded")
            self.warnings += 1

        (self.root / self.QDRANT_DATA_DIR).mkdir(parents=True, exist_ok=True)
        self.ok(f"Qdrant path ready: {self.QDRANT_DATA_DIR}")

        db_path = self.root / self.SQLITE_DB
        db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            con = sqlite3.connect(db_path)
            con.execute("PRAGMA integrity_check").fetchone()
            con.close()
            self.ok(f"SQLite registry OK: {self.SQLITE_DB}")
        except Exception:
            self.warn("SQLite registry check failed; app will initialize schema on startup")
            self.warnings += 1

        for path in [
            "data/raw",
            "data/parsed",
            "data/page_images",
            "data/tables",
            "data/figures",
            "data/reports",
            "data/indexes",
        ]:
            (self.root / path).mkdir(parents=True, exist_ok=True)
        self.ok("Data directories ready")

    def check_ports(self) -> None:
        self.header("Port Check")
        for port in [self.API_PORT, self.WEB_PORT]:
            self.free_port(port)

    def port_pids(self, port: int) -> list[int]:
        result = self.run_text(["lsof", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"])
        if result.returncode != 0:
            return []
        return [int(line) for line in result.stdout.splitlines() if line.strip().isdigit()]

    def free_port(self, port: int) -> None:
        pids = self.port_pids(port)
        if not pids:
            self.ok(f"Port {port} is free")
            return
        self.warn(f"Port {port} in use (PID(s): {' '.join(map(str, pids))}) — killing …")
        for pid in pids:
            self.kill_pid(pid, signal.SIGTERM)
        time.sleep(1)
        survivors = self.port_pids(port)
        for pid in survivors:
            self.kill_pid(pid, signal.SIGKILL)
        time.sleep(1)
        if self.port_pids(port):
            self.fail(f"Could not free port {port} — please release it manually and retry")
            self.errors += 1
        else:
            self.ok(f"Port {port} freed")

    def check_mcp(self) -> None:
        self.header("MCP Server (stdio transport)")
        result = self.run([str(self.venv_python), "-c", f"import {self.MCP_MODULE}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode == 0:
            self.ok(f"MCP server module importable ({self.MCP_MODULE})")
        else:
            self.fail(f"MCP server module failed to import — check {self.MCP_MODULE} and its dependencies")
            self.errors += 1

    def print_health_summary(self) -> None:
        print(f"\n{Style.BOLD}══════════════════════════════════════════{Style.RESET}", flush=True)
        if self.errors:
            self.fail(f"Health check: {self.errors} error(s), {self.warnings} warning(s)")
            print(f"{Style.RED}Cannot start — free the occupied ports or adjust start.py.{Style.RESET}", flush=True)
        elif self.warnings:
            self.warn(f"Health check: 0 errors, {self.warnings} warning(s)")
            print(f"{Style.YELLOW}Starting with degraded optional functionality …{Style.RESET}", flush=True)
        else:
            self.ok("All checks passed")
        print(f"{Style.BOLD}══════════════════════════════════════════{Style.RESET}\n", flush=True)

    def launch_services(self) -> None:
        self.header("Launch")
        self.info(f"Starting API on http://localhost:{self.API_PORT}")
        self.api_proc = subprocess.Popen(
            [str(self.venv_python), "-m", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", str(self.API_PORT)],
            cwd=str(self.root),
        )
        self.info(f"Starting UI on http://localhost:{self.WEB_PORT}")
        web_env = {**os.environ, "NEXT_PUBLIC_API_URL": f"http://localhost:{self.API_PORT}"}
        self.web_proc = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=str(self.root / self.FRONTEND_DIR),
            env=web_env,
        )
        subprocess.Popen(
            [sys.executable, "-c", f"import time, webbrowser; time.sleep(3); webbrowser.open('http://localhost:{self.WEB_PORT}')"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.info("Press Ctrl+C to stop both services")

    def monitor_services(self) -> int:
        while True:
            if self.api_proc and self.api_proc.poll() is not None:
                return self.handle_process_exit("FastAPI", self.api_proc.pid)
            if self.web_proc and self.web_proc.poll() is not None:
                return self.handle_process_exit("Next.js", self.web_proc.pid)
            time.sleep(2)

    def register_signal_handlers(self) -> None:
        def _handler(signum, _frame) -> None:
            self.cleanup()
            raise SystemExit(128 + signum)

        signal.signal(signal.SIGINT, _handler)
        signal.signal(signal.SIGTERM, _handler)

    def update_handoff_requested(self) -> bool:
        marker = self.root / self.UPDATE_HANDOFF_FILE
        if not marker.exists():
            return False
        age = time.time() - marker.stat().st_mtime
        if age > self.UPDATE_HANDOFF_TTL_SECONDS:
            marker.unlink(missing_ok=True)
            return False
        return True

    def handle_process_exit(self, process_name: str, pid: int) -> int:
        if self.update_handoff_requested():
            self.info("Update restart in progress; handing service control to the Python updater")
            return 0
        self.fail(f"{process_name} process exited unexpectedly (PID {pid})")
        self.cleanup()
        return 1

    def cleanup(self) -> None:
        print("", flush=True)
        self.info("Shutting down MiraDocs …")
        for proc in [self.web_proc, self.api_proc]:
            if proc and proc.poll() is None:
                proc.terminate()
        time.sleep(1)
        for proc in [self.web_proc, self.api_proc]:
            if proc and proc.poll() is None:
                proc.kill()
        for port in [self.API_PORT, self.WEB_PORT]:
            pids = self.port_pids(port)
            if pids:
                self.warn(f"Force-releasing port {port} (PIDs: {' '.join(map(str, pids))})")
                for pid in pids:
                    self.kill_pid(pid, signal.SIGKILL)
        self.ok("All ports released — goodbye!")

    def kill_pid(self, pid: int, sig: signal.Signals) -> None:
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            return
        except PermissionError:
            self.warn(f"No permission to signal PID {pid}")

    def write_status(self, status: str, message: str, version: str = "") -> None:
        status_file = self.root / self.STATUS_FILE
        status_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "status": status,
            "message": message,
            "version": version,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        status_file.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")

    def log(self, message: str) -> None:
        log_file = self.root / self.LOG_FILE
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as fh:
            fh.write(f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n")

    def run_update(self, *, mode: str = "detached") -> int:
        os.chdir(self.root)
        startup_mode = mode == "startup"
        (self.root / "data").mkdir(parents=True, exist_ok=True)
        (self.root / self.LOG_FILE).write_text("", encoding="utf-8")
        current_version = self.local_version()
        self.write_status("updating", "Starting update...", current_version)
        self.log("=== MiraDocs Update Started ===")
        if not startup_mode:
            time.sleep(2)

        marker = self.root / self.UPDATE_HANDOFF_FILE
        try:
            self.log("Stopping services...")
            self.write_status("updating", "Stopping services...", current_version)
            marker.write_text(f"{os.getpid()}\n", encoding="utf-8")
            # Kill by port first (most reliable) then fall back to pattern
            for port in [self.API_PORT, self.WEB_PORT]:
                for pid in self.port_pids(port):
                    self.kill_pid(pid, signal.SIGTERM)
            for pattern in [
                "uvicorn src.api.main:app",
                "next dev",
                "next start",
            ]:
                self.run(["pkill", "-f", pattern], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(2 if not startup_mode else 0)
            self.log("Services stopped.")

            prev_commit = self.run_text(["git", "rev-parse", "HEAD"]).stdout.strip()
            prev_version = self.local_version()
            self.log(f"Previous version: {prev_version} ({prev_commit})")
            self.log("Pulling latest changes...")
            self.write_status("updating", "Pulling latest changes...", prev_version)
            stashed = self.stash_tracked_changes_if_needed()
            if not self.git_pull_latest(prev_version):
                return 1
            if stashed:
                self.log("Restoring stashed local changes...")
                self.run_to_log(["git", "stash", "pop"], warn_on_failure="WARNING: git stash pop failed — stash preserved as stash@{0}")

            new_version = self.local_version()
            self.log(f"New version: {new_version}")
            self.log("Checking dependencies...")
            self.write_status("updating", "Installing dependencies...", new_version)
            self.install_changed_dependencies(prev_commit)
            self.log("Restarting services...")
            self.write_status("updating", "Restarting services...", new_version)
            if startup_mode:
                self.write_status("success", f"Updated to {new_version}. Startup will continue.", new_version)
                self.log("Startup update complete; returning control to start.py.")
                return 0
            return self.restart_after_update(new_version)
        finally:
            marker.unlink(missing_ok=True)

    def run_to_log(self, args: list[str], *, cwd: Path | None = None, warn_on_failure: str | None = None) -> bool:
        with (self.root / self.LOG_FILE).open("a", encoding="utf-8") as log_fh:
            result = self.run(args, cwd=cwd, stdout=log_fh, stderr=log_fh)
        if result.returncode != 0 and warn_on_failure:
            self.log(warn_on_failure)
        return result.returncode == 0

    def stash_tracked_changes_if_needed(self) -> bool:
        diff = self.run(["git", "diff", "--quiet"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if diff.returncode == 0:
            return False
        self.log("Stashing local changes...")
        return self.run_to_log(["git", "stash"], warn_on_failure="WARNING: git stash failed — continuing anyway")

    def git_pull_latest(self, prev_version: str) -> bool:
        if self.run_to_log(["git", "pull", "--ff-only"]):
            return True
        self.log("ERROR: git pull failed. Attempting reset...")
        self.run_to_log(["git", "fetch", "origin"])
        if self.run_to_log(["git", "reset", "--hard", "origin/main"]):
            return True
        self.write_status("failed", "Git pull failed. Manual intervention required.", prev_version)
        self.log("FATAL: Could not update from remote.")
        return False

    def install_changed_dependencies(self, prev_commit: str) -> None:
        req_changed = self.run(["git", "diff", "--quiet", prev_commit, "HEAD", "--", "requirements.txt"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0
        if req_changed:
            self.log("requirements.txt changed — reinstalling Python deps...")
            self.run_to_log([str(self.venv_pip), "install", "-r", "requirements.txt"])
        package_changed = self.run(["git", "diff", "--quiet", prev_commit, "HEAD", "--", f"{self.FRONTEND_DIR}/package.json"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0
        if package_changed:
            self.log("package.json changed — reinstalling Node deps...")
            self.run_to_log(["npm", "install"], cwd=self.root / self.FRONTEND_DIR)

    def restart_after_update(self, new_version: str) -> int:
        log_file = self.root / self.LOG_FILE
        with log_file.open("a", encoding="utf-8") as log_fh:
            subprocess.Popen(
                [sys.executable, str(self.root / "start.py"), "start", "--skip-start-update"],
                cwd=str(self.root),
                env={**os.environ, "MIRADOCS_SKIP_START_UPDATE": "1"},
                stdout=log_fh,
                stderr=log_fh,
                start_new_session=True,
            )
        self.log("Waiting for API to come up...")
        for _ in range(30):
            try:
                with urllib.request.urlopen(f"http://localhost:{self.API_PORT}/api/health", timeout=2):
                    self.log("API is healthy.")
                    self.write_status("success", f"Updated to {new_version}", new_version)
                    self.log("=== Update Complete ===")
                    return 0
            except Exception:
                time.sleep(2)
        self.write_status("failed", "Services failed to restart after update.", new_version)
        self.log("ERROR: Services did not become healthy within 60s.")
        return 1


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MiraDocs launcher and updater")
    parser.add_argument("command", nargs="?", choices=["start", "update"], default="start")
    parser.add_argument("--skip-start-update", action="store_true")
    parser.add_argument("--startup", action="store_true", help="Run update in startup mode")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    launcher = Launcher()
    if args.command == "update":
        return launcher.run_update(mode="startup" if args.startup else "detached")
    return launcher.start(skip_start_update=args.skip_start_update)


if __name__ == "__main__":
    raise SystemExit(main())
