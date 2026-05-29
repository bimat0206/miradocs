import importlib.util
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_start_module():
    spec = importlib.util.spec_from_file_location("miradocs_start", ROOT / "start.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_startup_update_runs_integrated_python_update(tmp_path, capsys):
    module = _load_start_module()
    (tmp_path / "VERSION").write_text("1.0.0\n", encoding="utf-8")

    class FakeLauncher(module.Launcher):
        def __init__(self):
            super().__init__(root=tmp_path, env={"MIRADOCS_START_UPDATE_ONLY": "1"})
            self.update_modes = []

        def github_repo_from_origin(self):
            return "example/miradocs"

        def remote_main_version(self, repo):
            assert repo == "example/miradocs"
            return "1.1.0"

        def run_update(self, *, mode="detached"):
            self.update_modes.append(mode)
            return 0

    launcher = FakeLauncher()

    assert launcher.check_startup_update() is True
    assert launcher.update_modes == ["startup"]
    output = capsys.readouterr().out
    assert "Update available: 1.0.0 -> 1.1.0" in output
    assert "Running integrated Python updater" in output
    assert "Restarting MiraDocs from the updated Python launcher" in output


def test_startup_update_check_skips_when_guard_is_set(tmp_path):
    module = _load_start_module()
    (tmp_path / "VERSION").write_text("1.0.0\n", encoding="utf-8")

    class FakeLauncher(module.Launcher):
        def github_repo_from_origin(self):
            raise AssertionError("git remote should not be checked when startup update is skipped")

    launcher = FakeLauncher(root=tmp_path, env={"MIRADOCS_SKIP_START_UPDATE": "1"})

    assert launcher.check_startup_update() is False


def test_start_exits_without_cleanup_during_update_handoff(tmp_path, capsys):
    module = _load_start_module()
    handoff_file = tmp_path / "data" / "update-restart-requested"
    handoff_file.parent.mkdir()
    handoff_file.write_text("123\n", encoding="utf-8")

    class FakeLauncher(module.Launcher):
        def __init__(self):
            super().__init__(root=tmp_path, env={})
            self.cleanup_called = False

        def cleanup(self):
            self.cleanup_called = True

    launcher = FakeLauncher()

    assert launcher.handle_process_exit("Next.js", 12345) == 0
    assert launcher.cleanup_called is False
    assert "Update restart in progress" in capsys.readouterr().out


def test_shell_scripts_delegate_to_python_launcher():
    start_sh = (ROOT / "start.sh").read_text(encoding="utf-8")
    update_sh = (ROOT / "update.sh").read_text(encoding="utf-8")

    assert 'python3 "$SCRIPT_DIR/start.py" "$@"' in start_sh
    assert 'python3 "$SCRIPT_DIR/start.py" update "$@"' in update_sh
    assert "git pull" not in update_sh
    assert "pkill" not in update_sh


def test_api_update_endpoint_uses_python_launcher():
    api_main = (ROOT / "src" / "api" / "main.py").read_text(encoding="utf-8")

    assert 'root / "start.py"' in api_main
    assert '"update"' in api_main
    assert 'root / "update.sh"' not in api_main


def test_startup_update_only_cli_exits_before_environment_checks(tmp_path):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    for name in ["start.py", "start.sh"]:
        src = ROOT / name
        dest = app_dir / name
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        dest.chmod(src.stat().st_mode)
    (app_dir / "VERSION").write_text("1.0.0\n", encoding="utf-8")

    result = subprocess.run(
        ["python3", "start.py"],
        cwd=app_dir,
        env={**os.environ, "MIRADOCS_START_UPDATE_ONLY": "1", "MIRADOCS_SKIP_START_UPDATE": "1"},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Environment" not in result.stdout
