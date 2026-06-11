from __future__ import annotations

import subprocess
from pathlib import Path

from hy3d_v2.hy3d_core.job_service import HY3DError, build_job_paths, import_result_package
from hy3d_v2.hy3d_core.utils.files import read_json

from .job_registry import update_status
from .settings import Settings


def _configured(settings: Settings) -> bool:
    return bool(settings.engine_root and settings.wrapper_run and settings.engine_root.exists() and settings.wrapper_run.exists())


def run_engine_for_job(
    settings: Settings,
    job_id: str,
    input_image: Path,
    version_id: str = "v1",
    repair_profile: str = "safe_light",
) -> dict:
    paths = build_job_paths(settings.workspace_root, job_id, version_id)
    update_status(settings.workspace_root, job_id, "running", "Running remote engine.")

    if settings.fixture_result_package and settings.fixture_result_package.exists():
        manifest = import_result_package(
            settings.workspace_root,
            job_id,
            settings.fixture_result_package,
            version_id=version_id,
            repair_profile=repair_profile,
        )
        update_status(settings.workspace_root, job_id, "candidate_ready_for_review", "Candidate ready for manual review.")
        return manifest

    if not _configured(settings):
        message = "HY3D_ENGINE_ROOT or HY3D_WRAPPER_RUN is not configured"
        update_status(settings.workspace_root, job_id, "failed", message)
        raise HY3DError(message)

    assert settings.engine_root is not None
    assert settings.wrapper_run is not None
    command = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(settings.wrapper_run),
        "-input_image",
        str(input_image),
        "-output_dir",
        str(paths.engine_output_dir),
        "-job_id",
        job_id,
        "-version_id",
        version_id,
        "-engine_root",
        str(settings.engine_root),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=settings.job_timeout_seconds, check=False)
    run_report_path = paths.engine_output_dir / "run_report.json"
    if not run_report_path.exists():
        message = f"run_report.json was not created. Exit code: {completed.returncode}"
        update_status(settings.workspace_root, job_id, "failed", message)
        raise HY3DError(message)
    run_report = read_json(run_report_path)
    if run_report.get("success") is not True:
        message = str(run_report.get("error") or completed.stderr or completed.stdout or "Remote engine failed.")
        update_status(settings.workspace_root, job_id, "failed", message)
        raise HY3DError(message)
    result_package = Path(str(run_report.get("result_package") or paths.engine_output_dir / "result_package.zip"))
    if not result_package.exists():
        message = "result_package.zip was not created"
        update_status(settings.workspace_root, job_id, "failed", message)
        raise HY3DError(message)
    manifest = import_result_package(
        settings.workspace_root,
        job_id,
        result_package,
        version_id=version_id,
        repair_profile=repair_profile,
    )
    update_status(settings.workspace_root, job_id, "candidate_ready_for_review", "Candidate ready for manual review.")
    return manifest

