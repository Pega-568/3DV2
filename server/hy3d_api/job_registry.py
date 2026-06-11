from __future__ import annotations

from pathlib import Path

from hy3d_v2.hy3d_core.job_service import build_job_paths
from hy3d_v2.hy3d_core.utils.files import read_json, utc_now_iso, write_json

STATUS_FILE = "server_job_status.json"


def status_path(root: Path, job_id: str) -> Path:
    return build_job_paths(root, job_id).job_dir / STATUS_FILE


def create_status(root: Path, job_id: str, status: str, message: str) -> dict:
    now = utc_now_iso()
    payload = {
        "job_id": job_id,
        "status": status,
        "message": message,
        "created_at": now,
        "updated_at": now,
    }
    write_json(status_path(root, job_id), payload)
    return payload


def update_status(root: Path, job_id: str, status: str, message: str) -> dict:
    path = status_path(root, job_id)
    payload = read_json(path) if path.exists() else create_status(root, job_id, status, message)
    payload["status"] = status
    payload["message"] = message
    payload["updated_at"] = utc_now_iso()
    write_json(path, payload)
    return payload


def get_status(root: Path, job_id: str) -> dict:
    path = status_path(root, job_id)
    if not path.exists():
        raise FileNotFoundError(job_id)
    return read_json(path)

