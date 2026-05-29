import os
import shutil
import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _copy_start_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    app_dir = tmp_path / "app"
    bin_dir = tmp_path / "bin"
    app_dir.mkdir()
    bin_dir.mkdir()
    shutil.copy(ROOT / "start.sh", app_dir / "start.sh")
    (app_dir / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    (app_dir / "update.sh").write_text(
        "#!/usr/bin/env bash\n"
        "echo \"skip=${MIRADOCS_SKIP_START_UPDATE:-} mode=${MIRADOCS_UPDATE_MODE:-}\" > update-called.txt\n",
        encoding="utf-8",
    )
    (app_dir / "update.sh").chmod(0o755)
    return app_dir, bin_dir, app_dir / "start.sh"


def _run_start_update_check(app_dir: Path, bin_dir: Path, start_script: Path) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "MIRADOCS_START_UPDATE_ONLY": "1",
        "NO_COLOR": "1",
    }
    return subprocess.run(
        ["bash", str(start_script)],
        cwd=app_dir,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_start_runs_update_script_when_remote_version_differs(tmp_path):
    app_dir, bin_dir, start_script = _copy_start_fixture(tmp_path)
    _write_executable(
        bin_dir / "git",
        "#!/usr/bin/env bash\n"
        "if [[ \"$*\" == \"remote get-url origin\" ]]; then\n"
        "  echo 'https://github.com/example/miradocs.git'\n"
        "  exit 0\n"
        "fi\n"
        "exit 1\n",
    )
    _write_executable(bin_dir / "curl", "#!/usr/bin/env bash\necho '1.1.0'\n")

    result = _run_start_update_check(app_dir, bin_dir, start_script)

    assert result.returncode == 0, result.stderr
    assert (app_dir / "update-called.txt").read_text(encoding="utf-8") == "skip=1 mode=startup\n"
    assert "Update available: 1.0.0 -> 1.1.0" in result.stdout
    assert "Restarting MiraDocs from the updated start.sh" in result.stdout
    assert "Environment" not in result.stdout


def test_start_update_check_continues_when_versions_match(tmp_path):
    app_dir, bin_dir, start_script = _copy_start_fixture(tmp_path)
    _write_executable(
        bin_dir / "git",
        "#!/usr/bin/env bash\n"
        "if [[ \"$*\" == \"remote get-url origin\" ]]; then\n"
        "  echo 'https://github.com/example/miradocs.git'\n"
        "  exit 0\n"
        "fi\n"
        "exit 1\n",
    )
    _write_executable(bin_dir / "curl", "#!/usr/bin/env bash\necho '1.0.0'\n")

    result = _run_start_update_check(app_dir, bin_dir, start_script)

    assert result.returncode == 0, result.stderr
    assert not (app_dir / "update-called.txt").exists()
    assert "Environment" not in result.stdout


def test_start_update_check_is_skipped_when_guard_is_set(tmp_path):
    app_dir, bin_dir, start_script = _copy_start_fixture(tmp_path)
    _write_executable(
        bin_dir / "git",
        "#!/usr/bin/env bash\n"
        "echo 'git should not be called' >&2\n"
        "exit 99\n",
    )
    _write_executable(bin_dir / "curl", "#!/usr/bin/env bash\nexit 99\n")

    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "MIRADOCS_SKIP_START_UPDATE": "1",
        "MIRADOCS_START_UPDATE_ONLY": "1",
    }
    result = subprocess.run(
        ["bash", str(start_script)],
        cwd=app_dir,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not (app_dir / "update-called.txt").exists()


def test_start_exits_without_cleanup_during_update_handoff(tmp_path):
    app_dir, bin_dir, start_script = _copy_start_fixture(tmp_path)
    handoff_file = app_dir / "data" / "update-restart-requested"
    handoff_file.parent.mkdir()
    handoff_file.write_text("123\n", encoding="utf-8")

    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "MIRADOCS_TEST_UPDATE_HANDOFF_EXIT": "1",
    }
    result = subprocess.run(
        ["bash", str(start_script)],
        cwd=app_dir,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Update restart in progress" in result.stdout
    assert "Shutting down MiraDocs" not in result.stdout
    assert "Next.js process exited unexpectedly" not in result.stdout
