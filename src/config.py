"""Application configuration loader."""
from pathlib import Path
import yaml

_CONFIG: dict | None = None
_ROOT = Path(__file__).resolve().parent.parent


def get_config() -> dict:
    global _CONFIG
    if _CONFIG is None:
        cfg_path = _ROOT / "config" / "settings.yaml"
        with open(cfg_path) as f:
            _CONFIG = yaml.safe_load(f)
    return _CONFIG


def get_data_dir() -> Path:
    return _ROOT / get_config()["app"]["data_dir"]


def get_db_path() -> Path:
    return _ROOT / get_config()["app"]["db_path"]
