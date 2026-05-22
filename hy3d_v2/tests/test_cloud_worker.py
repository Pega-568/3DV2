from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from hy3d_v2.blender_addon import (
    _cloud_names,
    _cloud_status_path,
    _ensure_cloud_directories,
    check_cloud_results,
    send_job_to_cloud,
)
from hy3d_v2.hy3d_core.job_service import HY3DError, create_job, create_job_package


ASSETS_DIR = Path(__file__).resolve().parents[1] / "test_assets"


@pytest.fixture()
def sample_input_png(tmp_path: Path) -> Path:
    target = tmp_path / "sample_input.png"
    shutil.copy2(ASSETS_DIR / "sample_input.png", target)
    return target


@pytest.fixture()
def sample_result_package(tmp_path: Path) -> Path:
    target = tmp_path / "result_package_sample.zip"
    shutil.copy2(ASSETS_DIR / "result_package_sample.zip", target)
    return target


@pytest.fixture()
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "hy3d_v2"
    (root / "jobs").mkdir(parents=True)
    return root


@pytest.fixture()
def cloud_root(tmp_path: Path) -> Path:
    root = tmp_path / "HY3D_V2_CLOUD"
    root.mkdir(parents=True)
    return root


def test_send_job_to_cloud_copies_zip_and_creates_status(project_root: Path, sample_input_png: Path, cloud_root: Path) -> None:
    manifest = create_job(project_root, sample_input_png)
    create_job_package(project_root, manifest["job_id"])

    payload = send_job_to_cloud(project_root, manifest["job_id"], cloud_root)
    names = _cloud_names(manifest["job_id"])
    incoming_zip = cloud_root / "incoming" / names["job_package"]

    assert payload["status"] == "sent_to_cloud"
    assert incoming_zip.exists()
    cloud_status = json.loads(_cloud_status_path(project_root, manifest["job_id"]).read_text(encoding="utf-8"))
    assert cloud_status["expected_result_package"] == names["result_package"]
    assert cloud_status["expected_status_json"] == names["status_json"]


def test_check_cloud_results_detects_completed_package(project_root: Path, sample_input_png: Path, sample_result_package: Path, cloud_root: Path) -> None:
    manifest = create_job(project_root, sample_input_png)
    create_job_package(project_root, manifest["job_id"])
    send_job_to_cloud(project_root, manifest["job_id"], cloud_root)
    names = _cloud_names(manifest["job_id"])
    completed_zip = cloud_root / "completed" / names["result_package"]
    completed_status = cloud_root / "completed" / names["status_json"]
    shutil.copy2(sample_result_package, completed_zip)
    completed_status.write_text(
        json.dumps(
            {
                "job_id": manifest["job_id"],
                "version_id": "v1",
                "engine_id": "triposr_clean",
                "status": "completed",
                "result_package": names["result_package"],
                "started_at": "2026-05-20T00:00:00+00:00",
                "finished_at": "2026-05-20T00:05:00+00:00",
                "error": None,
            }
        ),
        encoding="utf-8",
    )

    payload = check_cloud_results(project_root, manifest["job_id"], cloud_root)

    assert payload["status"] == "completed"
    assert payload["result_package_path"] == str(completed_zip)


def test_check_cloud_results_not_ready(project_root: Path, sample_input_png: Path, cloud_root: Path) -> None:
    manifest = create_job(project_root, sample_input_png)
    create_job_package(project_root, manifest["job_id"])
    send_job_to_cloud(project_root, manifest["job_id"], cloud_root)

    payload = check_cloud_results(project_root, manifest["job_id"], cloud_root)

    assert payload["status"] == "sent_to_cloud"


def test_check_cloud_results_detects_failed_error(project_root: Path, sample_input_png: Path, cloud_root: Path) -> None:
    manifest = create_job(project_root, sample_input_png)
    create_job_package(project_root, manifest["job_id"])
    send_job_to_cloud(project_root, manifest["job_id"], cloud_root)
    names = _cloud_names(manifest["job_id"])
    failed_error = cloud_root / "failed" / names["error_json"]
    failed_error.write_text(
        json.dumps(
            {
                "job_id": manifest["job_id"],
                "engine_id": "triposr_clean",
                "status": "failed",
                "error": "TripoSR failed",
                "traceback": "stack",
                "failed_at": "2026-05-20T00:10:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    payload = check_cloud_results(project_root, manifest["job_id"], cloud_root)

    assert payload["status"] == "failed"
    assert payload["error"] == "TripoSR failed"


def test_cloud_root_empty_is_not_treated_as_dot(project_root: Path, sample_input_png: Path) -> None:
    manifest = create_job(project_root, sample_input_png)
    create_job_package(project_root, manifest["job_id"])
    with pytest.raises(HY3DError, match="Cloud root folder"):
        send_job_to_cloud(project_root, manifest["job_id"], "")


def test_cloud_folders_are_created_if_missing(cloud_root: Path) -> None:
    directories = _ensure_cloud_directories(cloud_root)
    for name in ("incoming", "processing", "completed", "failed", "logs", "notebooks"):
        assert directories[name].exists()
        assert directories[name].is_dir()


def test_cloud_file_names_follow_contract() -> None:
    names = _cloud_names("job_abc123")
    assert names["job_package"] == "job_abc123_job_package.zip"
    assert names["result_package"] == "job_abc123_result_package.zip"
    assert names["status_json"] == "job_abc123_status.json"

