import importlib.util
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import src.api.main as api_main
from src.api.main import create_app


ROOT = Path(__file__).resolve().parents[1]


def _load_start_module():
    spec = importlib.util.spec_from_file_location("miradocs_start", ROOT / "start.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_startup_update_skips_when_remote_version_is_older(tmp_path, monkeypatch):
    module = _load_start_module()
    (tmp_path / "VERSION").write_text("1.7.2\n", encoding="utf-8")
    monkeypatch.setattr("builtins.input", lambda: (_ for _ in ()).throw(AssertionError("should not prompt")))

    class FakeLauncher(module.Launcher):
        def github_repo_from_origin(self):
            return "example/miradocs"

        def remote_main_version(self, repo):
            assert repo == "example/miradocs"
            return "1.7.1"

        def run_update(self, *, mode="detached"):
            raise AssertionError("should not update to an older version")

    assert FakeLauncher(root=tmp_path, env={}).check_startup_update() is False


def test_stale_update_handoff_marker_is_removed(tmp_path):
    module = _load_start_module()
    handoff_file = tmp_path / "data" / "update-restart-requested"
    handoff_file.parent.mkdir()
    handoff_file.write_text("123\n", encoding="utf-8")
    stale_time = time.time() - module.Launcher.UPDATE_HANDOFF_TTL_SECONDS - 1
    os.utime(handoff_file, (stale_time, stale_time))

    launcher = module.Launcher(root=tmp_path, env={})

    assert launcher.update_handoff_requested() is False
    assert not handoff_file.exists()


def test_git_pull_fallback_resets_current_upstream_not_main(tmp_path):
    module = _load_start_module()
    commands = []

    class FakeLauncher(module.Launcher):
        def run_to_log(self, args, *, cwd=None, warn_on_failure=None):
            commands.append(args)
            if args == ["git", "pull", "--ff-only"]:
                return False
            if args == ["git", "fetch", "origin"]:
                return True
            if args == ["git", "reset", "--hard", "origin/release/v1.7.0"]:
                return True
            return False

        def run_text(self, args, *, cwd=None, timeout=None):
            if args == ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]:
                return subprocess.CompletedProcess(args, 0, "origin/release/v1.7.0\n", "")
            return subprocess.CompletedProcess(args, 1, "", "unexpected")

    assert FakeLauncher(root=tmp_path, env={}).git_pull_latest("1.7.0") is True
    assert ["git", "reset", "--hard", "origin/release/v1.7.0"] in commands
    assert ["git", "reset", "--hard", "origin/main"] not in commands


def test_stash_failure_aborts_before_pull(tmp_path):
    module = _load_start_module()
    (tmp_path / "VERSION").write_text("1.7.2\n", encoding="utf-8")
    calls = []

    class FakeLauncher(module.Launcher):
        def run(self, args, **kwargs):
            if args == ["git", "diff", "--quiet"]:
                return subprocess.CompletedProcess(args, 1)
            return subprocess.CompletedProcess(args, 0)

        def run_to_log(self, args, *, cwd=None, warn_on_failure=None):
            calls.append(args)
            if args == ["git", "stash"]:
                return False
            if args == ["git", "pull", "--ff-only"]:
                raise AssertionError("pull should not run after stash failure")
            return True

    launcher = FakeLauncher(root=tmp_path, env={})

    assert launcher.stash_tracked_changes_if_needed() is None
    assert calls == [["git", "stash"]]


def test_version_check_does_not_offer_older_remote_version(monkeypatch):
    client = TestClient(create_app())

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"1.7.1\n"

    monkeypatch.setattr(api_main, "_read_local_version", lambda: "1.7.2")
    monkeypatch.setattr(api_main, "_get_github_repo", lambda: "example/miradocs")
    monkeypatch.setattr(api_main, "_read_remote_main_version_from_git", lambda: None)

    with patch("urllib.request.urlopen", return_value=FakeResponse()):
        response = client.get("/api/version-check")

    assert response.status_code == 200
    assert response.json() == {
        "update_available": False,
        "local_version": "1.7.2",
        "remote_version": "1.7.1",
    }


def test_version_check_prefers_git_remote_version_over_raw_github(monkeypatch):
    client = TestClient(create_app())

    class FakeRawResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"1.7.2\n"

    def fake_run(args, **kwargs):
        if args == ["git", "fetch", "--quiet", "origin", "main"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        if args == ["git", "show", "FETCH_HEAD:VERSION"]:
            return subprocess.CompletedProcess(args, 0, "1.8.1\n", "")
        raise AssertionError(f"unexpected subprocess call: {args}")

    monkeypatch.setattr(api_main, "_read_local_version", lambda: "1.7.2")
    monkeypatch.setattr(api_main, "_get_github_repo", lambda: "example/miradocs")
    monkeypatch.setattr(subprocess, "run", fake_run)

    with patch("urllib.request.urlopen", return_value=FakeRawResponse()):
        response = client.get("/api/version-check")

    assert response.status_code == 200
    assert response.json() == {
        "update_available": True,
        "local_version": "1.7.2",
        "remote_version": "1.8.1",
    }


def test_update_status_marks_stale_updating_state_failed(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path))
    status_file = tmp_path / "update-status.json"
    stale_timestamp = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    status_file.write_text(
        '{"status":"updating","message":"Pulling latest changes...","version":"1.5.2","timestamp":"%s"}'
        % stale_timestamp,
        encoding="utf-8",
    )

    response = client.get("/api/update-status")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert "stale" in body["message"].lower()
