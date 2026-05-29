import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_release_version_metadata_is_consistent():
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    package_json = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    package_lock = json.loads((ROOT / "frontend" / "package-lock.json").read_text(encoding="utf-8"))
    mcp_server = (ROOT / "src" / "mcp" / "server.py").read_text(encoding="utf-8")

    assert version == "1.1.1"
    assert package_json["version"] == version
    assert package_lock["version"] == version
    assert package_lock["packages"][""]["version"] == version
    assert f'"version": "{version}"' in mcp_server


def test_release_changelog_is_present_and_ignored_by_default():
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert re.search(rf"^## v{re.escape(version)}\b", changelog, flags=re.MULTILINE)
    assert "CHANGELOG.md" in gitignore.splitlines()
