from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from hy3d_v2.blender_addon import (
    ADDON_BUILD_ID,
    _build_self_check_payload,
    _has_valid_accepted_model_path,
    _has_valid_candidate_path,
    _has_valid_result_package_path,
    _resolve_existing_file,
    _resolve_existing_dir,
    _ui_disables_candidate_import_without_candidate,
    _validate_primary_image_for_job_creation,
)
from hy3d_v2.hy3d_core.job_service import HY3DError, create_job, import_result_package


ASSETS_DIR = Path(__file__).resolve().parents[1] / "test_assets"


@pytest.fixture()
def sample_input_png(tmp_path: Path) -> Path:
    target = tmp_path / "sample_input.png"
    shutil.copy2(ASSETS_DIR / "sample_input.png", target)
    return target


@pytest.fixture()
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "hy3d_v2"
    (root / "jobs").mkdir(parents=True)
    return root


def test_empty_path_does_not_resolve_to_dot(tmp_path: Path) -> None:
    assert _resolve_existing_file("", suffix=".glb") is None
    assert _resolve_existing_file(".", suffix=".glb") is None
    assert _resolve_existing_dir("") is None
    assert _resolve_existing_dir(".") is None


def test_create_job_blocked_without_primary_image() -> None:
    path, error = _validate_primary_image_for_job_creation("")
    assert path is None
    assert error == "Please select a primary image before creating a job."


def test_create_job_rejects_dot_path() -> None:
    path, error = _validate_primary_image_for_job_creation(".")
    assert path is None
    assert error == "Invalid primary image path."


def test_create_job_rejects_directory_as_image(tmp_path: Path) -> None:
    path, error = _validate_primary_image_for_job_creation(str(tmp_path))
    assert path is None
    assert error == "Primary image path is not a file."


def test_import_candidate_blocked_without_result_package() -> None:
    props = SimpleNamespace(candidate_path="")
    assert _has_valid_candidate_path(props) is False


def test_import_candidate_blocked_without_model_glb(tmp_path: Path) -> None:
    fake_candidate = tmp_path / "missing.glb"
    props = SimpleNamespace(candidate_path=str(fake_candidate))
    assert _has_valid_candidate_path(props) is False


def test_export_stl_blocked_without_accepted_model() -> None:
    props = SimpleNamespace(accepted_model_path="")
    assert _has_valid_accepted_model_path(props) is False


def test_import_result_requires_zip_file(project_root: Path, sample_input_png: Path, tmp_path: Path) -> None:
    manifest = create_job(project_root, sample_input_png)
    not_zip = tmp_path / "result.txt"
    not_zip.write_text("no zip", encoding="utf-8")

    assert _has_valid_result_package_path(SimpleNamespace(result_package_path=str(not_zip))) is False
    with pytest.raises(HY3DError, match="valid \\.zip file"):
        import_result_package(project_root, manifest["job_id"], not_zip)


def test_ui_disables_candidate_import_without_candidate() -> None:
    props = SimpleNamespace(candidate_path="")
    assert _ui_disables_candidate_import_without_candidate(props) is True


def test_create_job_accepts_sample_input(sample_input_png: Path) -> None:
    path, error = _validate_primary_image_for_job_creation(str(sample_input_png))
    assert error is None
    assert path == sample_input_png


def test_addon_build_id_visible() -> None:
    assert ADDON_BUILD_ID.startswith("hy3d_v2_")


def test_self_check_reports_loaded_addon_path() -> None:
    props = SimpleNamespace(
        primary_image_path="",
        job_id="job_123",
        job_package_path="",
        result_package_path="",
        candidate_path="",
        accepted_model_path="",
    )
    payload = _build_self_check_payload(props)
    assert payload["build_id"] == ADDON_BUILD_ID
    assert payload["addon_path"].endswith(r"hy3d_v2\blender_addon\__init__.py")
