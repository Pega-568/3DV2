from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from typing import Iterable

from fastapi import HTTPException, UploadFile

from hy3d_v2.hy3d_core.job_service import build_job_paths
from hy3d_v2.hy3d_core.utils.files import ensure_dir

REPORT_NAMES = [
    "candidate_validation_report.json",
    "mesh_quality_report.json",
    "repair_comparison_report.json",
    "repair_report_light.json",
    "repair_report_meshfix.json",
    "repair_report_meshlab.json",
]

FINAL_PACKAGE_NAMES = [
    "accepted_model.glb",
    "accepted_model.stl",
    "stl_validation_report.json",
    "printability_report.json",
]


def save_upload(upload: UploadFile, destination: Path, max_upload_mb: int) -> Path:
    ensure_dir(destination.parent)
    max_bytes = max_upload_mb * 1024 * 1024
    total = 0
    with destination.open("wb") as dst:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                destination.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail=f"Upload exceeds HY3D_MAX_UPLOAD_MB={max_upload_mb}")
            dst.write(chunk)
    return destination


def public_candidate_manifest(candidate_manifest: dict) -> dict:
    candidates = {
        "original": "model.glb" if candidate_manifest.get("candidate_path") else None,
        "light": "repaired_candidate_light.glb" if candidate_manifest.get("repaired_candidate_light_path") else None,
        "meshfix": "repaired_candidate_meshfix.glb" if candidate_manifest.get("repaired_candidate_meshfix_path") else None,
        "meshlab": "repaired_candidate_meshlab.glb" if candidate_manifest.get("repaired_candidate_meshlab_path") else None,
    }
    return {
        "job_id": candidate_manifest.get("job_id"),
        "version_id": candidate_manifest.get("version_id"),
        "status": "candidate_ready_for_review",
        "candidates": candidates,
        "validation_status": candidate_manifest.get("validation_status"),
        "mesh_quality_status": candidate_manifest.get("mesh_quality_status"),
        "repair_recommended": candidate_manifest.get("repair_recommended"),
        "repair_profile": candidate_manifest.get("repair_profile"),
        "no_auto_acceptance": True,
    }


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Missing file: {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Invalid JSON: {path.name}") from exc


def zip_files(zip_path: Path, files: Iterable[tuple[Path, str]]) -> Path:
    ensure_dir(zip_path.parent)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source, arcname in files:
            if source.exists() and source.is_file():
                archive.write(source, arcname)
    return zip_path


def copy_to_exports(root: Path, exports_root: Path, job_id: str) -> Path:
    paths = build_job_paths(root, job_id)
    accepted_version = read_json(paths.manifests["job"]).get("active_accepted_version") or "v1"
    accepted_paths = build_job_paths(root, job_id, accepted_version)
    export_dir = exports_root / job_id
    ensure_dir(export_dir)
    for name in FINAL_PACKAGE_NAMES + ["repair_comparison_report.json", "job_summary_report.json"]:
        source = accepted_paths.accepted_dir / name
        if name == "repair_comparison_report.json":
            source = accepted_paths.validation_dir / name
        if name == "job_summary_report.json":
            source = paths.job_dir / name
        if source.exists() and source.is_file():
            shutil.copy2(source, export_dir / name)
    return export_dir

