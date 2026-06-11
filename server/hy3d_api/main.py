from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image

from hy3d_v2.hy3d_core.job_service import (
    HY3DError,
    build_job_paths,
    create_job,
    export_stl_from_accepted,
    promote_selected_object_to_accepted,
    simulate_copy_exporter,
)
from hy3d_v2.hy3d_core.utils.files import read_json, write_json

from .engine_runner import run_engine_for_job
from .job_registry import create_status, get_status, update_status
from .schemas import AcceptedResponse, ExportStlResponse, HealthResponse, JobCreateResponse, JobStatusResponse
from .settings import get_settings
from .storage import REPORT_NAMES, copy_to_exports, public_candidate_manifest, save_upload, zip_files

app = FastAPI(title="HY3D API", version="0.1.0")


def _settings():
    return get_settings()


def _image_suffix(upload: UploadFile) -> str:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".avif", ".bmp"}:
        raise HTTPException(status_code=400, detail="Unsupported image format")
    return suffix


def _validate_image(path: Path) -> None:
    try:
        with Image.open(path) as img:
            img.verify()
    except Exception as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Invalid image: {exc}") from exc


def _paths_or_404(job_id: str):
    settings = _settings()
    paths = build_job_paths(settings.workspace_root, job_id)
    if not paths.job_dir.exists():
        raise HTTPException(status_code=404, detail=f"Unknown job: {job_id}")
    return settings, paths


@app.get("/health", response_model=HealthResponse)
def health() -> dict:
    return {"status": "ok", "service": "hy3d-api"}


@app.post("/api/jobs", response_model=JobCreateResponse)
def create_remote_job(image: UploadFile = File(...), repair_profile: str = Form("safe_light")) -> dict:
    settings = _settings()
    suffix = _image_suffix(image)
    incoming = settings.workspace_root / "_incoming" / f"upload{suffix}"
    save_upload(image, incoming, settings.max_upload_mb)
    _validate_image(incoming)
    manifest = create_job(settings.workspace_root, incoming)
    job_id = manifest["job_id"]
    input_image = build_job_paths(settings.workspace_root, job_id).input_dir / f"primary_image{suffix}"
    create_status(settings.workspace_root, job_id, "queued", "Job created.")
    try:
        run_engine_for_job(settings, job_id, input_image, repair_profile=repair_profile)
    except HY3DError as exc:
        return {"job_id": job_id, "status": "failed", "error": str(exc)}
    return {"job_id": job_id, "status": "running"}


@app.get("/api/jobs/{job_id}/status", response_model=JobStatusResponse)
def job_status(job_id: str) -> dict:
    settings, _paths = _paths_or_404(job_id)
    try:
        return get_status(settings.workspace_root, job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown job: {job_id}") from exc


@app.get("/api/jobs/{job_id}/manifest")
def manifest(job_id: str) -> dict:
    _settings_obj, paths = _paths_or_404(job_id)
    manifest_path = paths.engine_output_dir / "candidate_manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="Candidate manifest is not available")
    return public_candidate_manifest(read_json(manifest_path))


def _candidate_response(job_id: str, candidate_type: str) -> FileResponse:
    _settings_obj, paths = _paths_or_404(job_id)
    names = {
        "original": "model.glb",
        "light": "repaired_candidate_light.glb",
        "meshfix": "repaired_candidate_meshfix.glb",
        "meshlab": "repaired_candidate_meshlab.glb",
    }
    path = paths.engine_output_dir / names[candidate_type]
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{candidate_type} candidate is not available")
    return FileResponse(path, media_type="model/gltf-binary", filename=path.name)


@app.get("/api/jobs/{job_id}/candidates/original")
def original_candidate(job_id: str) -> FileResponse:
    return _candidate_response(job_id, "original")


@app.get("/api/jobs/{job_id}/candidates/light")
def light_candidate(job_id: str) -> FileResponse:
    return _candidate_response(job_id, "light")


@app.get("/api/jobs/{job_id}/candidates/meshfix")
def meshfix_candidate(job_id: str) -> FileResponse:
    return _candidate_response(job_id, "meshfix")


@app.get("/api/jobs/{job_id}/candidates/meshlab")
def meshlab_candidate(job_id: str) -> FileResponse:
    return _candidate_response(job_id, "meshlab")


@app.get("/api/jobs/{job_id}/reports")
def reports(job_id: str) -> FileResponse:
    _settings_obj, paths = _paths_or_404(job_id)
    zip_path = paths.job_dir / "reports.zip"
    files = [(paths.validation_dir / name, name) for name in REPORT_NAMES]
    zip_files(zip_path, files)
    return FileResponse(zip_path, media_type="application/zip", filename="hy3d_reports.zip")


@app.post("/api/jobs/{job_id}/accepted", response_model=AcceptedResponse)
def upload_accepted(
    job_id: str,
    accepted_model: UploadFile = File(...),
    source_candidate_type: str | None = Form(None),
    notes: str | None = Form(None),
) -> dict:
    settings, paths = _paths_or_404(job_id)
    if not (paths.engine_output_dir / "candidate_manifest.json").exists():
        raise HTTPException(status_code=409, detail="Cannot accept before candidates are generated")
    if Path(accepted_model.filename or "").suffix.lower() != ".glb":
        raise HTTPException(status_code=400, detail="accepted_model must be a .glb file")
    temp_path = paths.accepted_dir / "_uploaded_accepted_model.glb"
    save_upload(accepted_model, temp_path, settings.max_upload_mb)
    accepted_path = promote_selected_object_to_accepted(
        settings.workspace_root,
        job_id,
        "v1",
        exporter=simulate_copy_exporter(temp_path),
        accepted_object_name="remote_blender_selection",
        source_candidate_path=source_candidate_type or "remote_upload",
        human_edited=True,
    )
    temp_path.unlink(missing_ok=True)
    accepted_manifest_path = paths.accepted_dir / "accepted_manifest.json"
    accepted_manifest = read_json(accepted_manifest_path)
    accepted_manifest["source_candidate_type"] = source_candidate_type
    accepted_manifest["notes"] = notes
    accepted_manifest["accepted_source"] = "remote_selected_blender_object"
    write_json(accepted_manifest_path, accepted_manifest)
    update_status(settings.workspace_root, job_id, "accepted", "Accepted model uploaded by Blender.")
    return {"job_id": job_id, "status": "accepted", "accepted_model": "accepted_model.glb"}


@app.post("/api/jobs/{job_id}/export-stl", response_model=ExportStlResponse)
def export_remote_stl(job_id: str) -> dict:
    settings, paths = _paths_or_404(job_id)
    accepted = paths.accepted_dir / "accepted_model.glb"
    if not accepted.exists():
        raise HTTPException(status_code=409, detail="accepted_model.glb is required before STL export")
    stl_path = export_stl_from_accepted(settings.workspace_root, job_id)
    copy_to_exports(settings.workspace_root, settings.exports_root, job_id)
    update_status(settings.workspace_root, job_id, "stl_exported", "STL exported from accepted_model.glb.")
    return {"job_id": job_id, "status": "stl_exported", "stl": stl_path.name}


@app.get("/api/jobs/{job_id}/final-package")
def final_package(job_id: str) -> FileResponse:
    _settings_obj, paths = _paths_or_404(job_id)
    accepted = paths.accepted_dir / "accepted_model.glb"
    stl = paths.accepted_dir / "accepted_model.stl"
    if not accepted.exists() or not stl.exists():
        raise HTTPException(status_code=409, detail="Final package is not available until STL export completes")
    zip_path = paths.job_dir / "final_package.zip"
    candidates = [
        (accepted, "accepted_model.glb"),
        (stl, "accepted_model.stl"),
        (paths.accepted_dir / "stl_validation_report.json", "stl_validation_report.json"),
        (paths.accepted_dir / "printability_report.json", "printability_report.json"),
        (paths.validation_dir / "repair_comparison_report.json", "repair_comparison_report.json"),
        (paths.job_dir / "job_summary_report.json", "job_summary_report.json"),
    ]
    zip_files(zip_path, candidates)
    return FileResponse(zip_path, media_type="application/zip", filename="hy3d_final_package.zip")

