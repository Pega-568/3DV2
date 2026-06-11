from __future__ import annotations

import json
import os
from pathlib import Path


CONFIG_ENV_KEYS = {
    "project_root": "HY3D_PROJECT_ROOT",
    "engine_root": "HY3D_ENGINE_ROOT",
    "wrapper_run": "HY3D_WRAPPER_RUN",
    "exports_root": "HY3D_EXPORTS_ROOT",
}


def get_repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def get_config_path(repo_root: Path | None = None) -> Path:
    env_path = os.environ.get("HY3D_CONFIG_PATH")
    if env_path:
        return Path(os.path.expandvars(os.path.expanduser(env_path)))
    return (repo_root or get_repo_root()) / "hy3d_local_config.json"


def load_local_config() -> dict[str, str]:
    path = get_config_path()
    if not path.exists() or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value) for key, value in payload.items() if value is not None and str(value).strip()}


def resolve_configured_path(value: str | Path, base_dir: Path) -> Path:
    raw = str(value).strip().strip('"').strip("'")
    if not raw:
        return Path("")
    expanded = os.path.expandvars(os.path.expanduser(raw))
    path = Path(expanded)
    if path.is_absolute():
        return path

    config_relative = (get_config_path().parent / path).resolve()
    if config_relative.exists():
        return config_relative
    return (base_dir / path).resolve()


def _configured_value(env_key: str, *config_keys: str) -> str | None:
    env_value = os.environ.get(env_key)
    if env_value:
        return env_value
    config = load_local_config()
    for key in (env_key, *config_keys):
        value = config.get(key)
        if value:
            return value
    return None


def _first_existing(candidates: list[Path]) -> Path | None:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def get_project_root() -> Path:
    repo_root = get_repo_root()
    value = _configured_value("HY3D_PROJECT_ROOT", "project_root")
    if value:
        return resolve_configured_path(value, repo_root)
    return repo_root / "hy3d_v2"


def get_engine_root() -> Path | None:
    repo_root = get_repo_root()
    value = _configured_value("HY3D_ENGINE_ROOT", "engine_root")
    if value:
        return resolve_configured_path(value, repo_root)
    existing = _first_existing(
        [
            repo_root.parent / "3D_ENGINES" / "triposr-local",
            repo_root / "external_engines" / "triposr-local",
            repo_root / "engines" / "triposr-local",
        ]
    )
    return existing or repo_root / "external_engines" / "triposr-local"


def get_wrapper_run() -> Path | None:
    repo_root = get_repo_root()
    value = _configured_value("HY3D_WRAPPER_RUN", "wrapper_run")
    if value:
        return resolve_configured_path(value, repo_root)
    return repo_root / "tools" / "triposr" / "run_triposr_local.ps1"


def get_exports_root() -> Path:
    repo_root = get_repo_root()
    value = _configured_value("HY3D_EXPORTS_ROOT", "exports_root")
    if value:
        return resolve_configured_path(value, repo_root)
    return repo_root / "HY3D_EXPORTS"
