from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from hy3d_v2.hy3d_core.job_service import create_job, create_job_package


CLEAN_ROOT = Path(__file__).resolve().parents[2] / "hy3d_v2_clean_addon"
if str(CLEAN_ROOT) not in sys.path:
    sys.path.insert(0, str(CLEAN_ROOT))

import hy3d_v2_clean  # noqa: E402


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


def test_clean_addon_has_unique_bl_info() -> None:
    assert hy3d_v2_clean.bl_info["name"] == "HY3D v2 Clean"
    assert hy3d_v2_clean.bl_info["location"] == "View3D > Sidebar > HY3D v2 Clean"


def test_clean_addon_no_legacy_operator_ids() -> None:
    source = (CLEAN_ROOT / "hy3d_v2_clean" / "__init__.py").read_text(encoding="utf-8")
    forbidden = [
        'bl_idname = "hy3d_v2.',
        "HY3D_PT_main_panel",
        "prefer_3d_if_safe",
        "Relief",
        "7A",
        "7B",
        "7C",
        "7X",
    ]
    for item in forbidden:
        assert item not in source


def test_clean_addon_uses_clean_workspace() -> None:
    assert "hy3d_v2_clean_workspace" in str(hy3d_v2_clean.workspace_root())


def test_clean_addon_sample_assets_exist() -> None:
    assert hy3d_v2_clean.SAMPLE_INPUT.exists()
    assert hy3d_v2_clean.SAMPLE_RESULT_PACKAGE.exists()


def test_select_primary_image_accepts_valid_image(sample_input_png: Path) -> None:
    path, error = hy3d_v2_clean._validate_primary_image(str(sample_input_png))
    assert error is None
    assert path == sample_input_png


def test_select_primary_image_rejects_empty_path() -> None:
    path, error = hy3d_v2_clean._validate_primary_image("")
    assert path is None
    assert error == "Please select a primary image before creating a job."


def test_select_primary_image_rejects_invalid_extension(tmp_path: Path) -> None:
    invalid_file = tmp_path / "bad.txt"
    invalid_file.write_text("x", encoding="utf-8")
    path, error = hy3d_v2_clean._validate_primary_image(str(invalid_file))
    assert path is None
    assert error == "Unsupported image format."


def test_clean_addon_does_not_use_dot_as_path() -> None:
    assert hy3d_v2_clean._resolve_existing_file(".", suffix=".glb") is None
    assert hy3d_v2_clean._resolve_existing_dir(".") is None
    path, error = hy3d_v2_clean._validate_primary_image(".")
    assert path is None
    assert error == "Invalid primary image path."


def test_send_job_to_cloud_copies_job_package_and_creates_status(tmp_path: Path, sample_input_png: Path) -> None:
    root = tmp_path / "hy3d_v2_clean_workspace"
    (root / "jobs").mkdir(parents=True)
    cloud_root = tmp_path / "HY3D_V2_CLOUD"
    cloud_root.mkdir(parents=True)
    manifest = create_job(root, sample_input_png)
    create_job_package(root, manifest["job_id"])

    payload = hy3d_v2_clean.send_job_to_cloud(root, manifest["job_id"], cloud_root)

    names = hy3d_v2_clean._cloud_names(manifest["job_id"])
    incoming_zip = cloud_root / "incoming" / names["job_package"]
    assert payload["status"] == hy3d_v2_clean.CLOUD_STATUS_SENT
    assert incoming_zip.exists()
    cloud_status_path = hy3d_v2_clean._cloud_status_path(root, manifest["job_id"])
    cloud_status = json.loads(cloud_status_path.read_text(encoding="utf-8"))
    assert cloud_status["incoming_package"] == str(incoming_zip)
    assert cloud_status["expected_result_package"] == names["result_package"]
    assert cloud_status["expected_status_json"] == names["status_json"]


def test_check_cloud_results_detects_completed(tmp_path: Path, sample_input_png: Path, sample_result_package: Path) -> None:
    root = tmp_path / "hy3d_v2_clean_workspace"
    (root / "jobs").mkdir(parents=True)
    cloud_root = tmp_path / "HY3D_V2_CLOUD"
    cloud_root.mkdir(parents=True)
    manifest = create_job(root, sample_input_png)
    create_job_package(root, manifest["job_id"])
    hy3d_v2_clean.send_job_to_cloud(root, manifest["job_id"], cloud_root)
    names = hy3d_v2_clean._cloud_names(manifest["job_id"])
    completed_zip = cloud_root / "completed" / names["result_package"]
    completed_zip.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(sample_result_package, completed_zip)
    (cloud_root / "completed" / names["status_json"]).write_text(
        json.dumps({"job_id": manifest["job_id"], "status": "completed"}, indent=2) + "\n",
        encoding="utf-8",
    )

    payload = hy3d_v2_clean.check_cloud_results(root, manifest["job_id"], cloud_root)

    assert payload["status"] == hy3d_v2_clean.CLOUD_STATUS_COMPLETED
    assert payload["result_package_path"] == str(completed_zip)


def test_check_cloud_results_detects_failed(tmp_path: Path, sample_input_png: Path) -> None:
    root = tmp_path / "hy3d_v2_clean_workspace"
    (root / "jobs").mkdir(parents=True)
    cloud_root = tmp_path / "HY3D_V2_CLOUD"
    cloud_root.mkdir(parents=True)
    manifest = create_job(root, sample_input_png)
    create_job_package(root, manifest["job_id"])
    hy3d_v2_clean.send_job_to_cloud(root, manifest["job_id"], cloud_root)
    names = hy3d_v2_clean._cloud_names(manifest["job_id"])
    failed_error = cloud_root / "failed" / names["error_json"]
    failed_error.parent.mkdir(parents=True, exist_ok=True)
    failed_error.write_text(
        json.dumps({"job_id": manifest["job_id"], "status": "failed", "error": "TripoSR failed"}, indent=2) + "\n",
        encoding="utf-8",
    )

    payload = hy3d_v2_clean.check_cloud_results(root, manifest["job_id"], cloud_root)

    assert payload["status"] == hy3d_v2_clean.CLOUD_STATUS_FAILED
    assert payload["error"] == "TripoSR failed"


def test_check_cloud_results_not_ready(tmp_path: Path, sample_input_png: Path) -> None:
    root = tmp_path / "hy3d_v2_clean_workspace"
    (root / "jobs").mkdir(parents=True)
    cloud_root = tmp_path / "HY3D_V2_CLOUD"
    cloud_root.mkdir(parents=True)
    manifest = create_job(root, sample_input_png)
    create_job_package(root, manifest["job_id"])

    payload = hy3d_v2_clean.check_cloud_results(root, manifest["job_id"], cloud_root)

    assert payload["status"] == hy3d_v2_clean.CLOUD_STATUS_NOT_READY


def test_import_cloud_result_reuses_import_result_package(tmp_path: Path, sample_input_png: Path, sample_result_package: Path) -> None:
    root = tmp_path / "hy3d_v2_clean_workspace"
    (root / "jobs").mkdir(parents=True)
    manifest = create_job(root, sample_input_png)
    create_job_package(root, manifest["job_id"])
    props = SimpleNamespace(
        job_id=manifest["job_id"],
        version_id="v1",
        result_package_path="",
        cloud_result_package_path=str(sample_result_package),
        candidate_model_path="",
        accepted_model_path="",
    )

    original_workspace_root = hy3d_v2_clean.workspace_root
    try:
        hy3d_v2_clean.workspace_root = lambda: root
        hy3d_v2_clean._import_result_package_into_session(props, sample_result_package)
    finally:
        hy3d_v2_clean.workspace_root = original_workspace_root

    assert props.result_package_path == str(sample_result_package)
    assert props.cloud_result_package_path == str(sample_result_package)
    assert props.candidate_model_path.endswith("model.glb")


def test_cloud_root_empty_is_not_treated_as_dot(tmp_path: Path, sample_input_png: Path) -> None:
    root = tmp_path / "hy3d_v2_clean_workspace"
    (root / "jobs").mkdir(parents=True)
    manifest = create_job(root, sample_input_png)
    create_job_package(root, manifest["job_id"])
    with pytest.raises(hy3d_v2_clean.HY3DError, match="Cloud root folder"):
        hy3d_v2_clean.send_job_to_cloud(root, manifest["job_id"], "")
