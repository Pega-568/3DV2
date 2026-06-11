from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_path(name: str, default: str | None = None) -> Path | None:
    value = os.environ.get(name, default)
    if value is None or not str(value).strip():
        return None
    return Path(str(value)).expanduser().resolve()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    workspace_root: Path
    exports_root: Path
    engine_root: Path | None
    wrapper_run: Path | None
    job_timeout_seconds: int
    max_upload_mb: int
    fixture_result_package: Path | None


def get_settings() -> Settings:
    workspace_root = _env_path("HY3D_SERVER_WORKSPACE_ROOT", "server_workspace")
    exports_root = _env_path("HY3D_SERVER_EXPORTS_ROOT", "server_exports")
    assert workspace_root is not None
    assert exports_root is not None
    workspace_root.mkdir(parents=True, exist_ok=True)
    exports_root.mkdir(parents=True, exist_ok=True)
    return Settings(
        workspace_root=workspace_root,
        exports_root=exports_root,
        engine_root=_env_path("HY3D_ENGINE_ROOT"),
        wrapper_run=_env_path("HY3D_WRAPPER_RUN"),
        job_timeout_seconds=_env_int("HY3D_JOB_TIMEOUT_SECONDS", 900),
        max_upload_mb=_env_int("HY3D_MAX_UPLOAD_MB", 25),
        fixture_result_package=_env_path("HY3D_SERVER_FIXTURE_RESULT_PACKAGE"),
    )

