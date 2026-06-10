from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from hy3d_local_connector_addon.hy3d_local_connector import _import_result_package_into_session
from hy3d_v2.hy3d_core.input_quality.service import analyze_input_image
from hy3d_v2.hy3d_core.job_service import HY3DError, create_job, export_active_accepted_stl, import_result_package
from hy3d_v2.hy3d_core.repair.service import run_repair_benchmark
from hy3d_v2.hy3d_core.utils.files import read_json


ASSETS_DIR = Path(__file__).resolve().parents[1] / "test_assets"


@pytest.fixture()
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "hy3d_v2"
    (root / "jobs").mkdir(parents=True)
    return root


@pytest.fixture()
def sample_input_png(tmp_path: Path) -> Path:
    target = tmp_path / "sample_input.png"
    shutil.copy2(ASSETS_DIR / "sample_input.png", target)
    return target


@pytest.fixture()
def sample_model_glb(tmp_path: Path) -> Path:
    target = tmp_path / "sample_model.glb"
    shutil.copy2(ASSETS_DIR / "sample_model.glb", target)
    return target


@pytest.fixture()
def result_package_sample(tmp_path: Path) -> Path:
    target = tmp_path / "result_package_sample.zip"
    shutil.copy2(ASSETS_DIR / "result_package_sample.zip", target)
    return target


def _write_image(path: Path, size: tuple[int, int], color=(128, 128, 128)) -> Path:
    Image = pytest.importorskip("PIL.Image")
    image = Image.new("RGB", size, color)
    image.save(path)
    return path


def test_analyze_input_image_valid_image(tmp_path: Path) -> None:
    image_path = _write_image(tmp_path / "valid.png", (512, 512), (10, 120, 240))

    report = analyze_input_image(image_path)

    assert report["exists"] is True
    assert report["width"] == 512
    assert report["height"] == 512
    assert report["is_square_or_near_square"] is True
    assert report["input_quality_status"] in {"ok", "warning"}
    assert "warnings" in report


def test_analyze_input_image_small_image_warns(tmp_path: Path) -> None:
    image_path = _write_image(tmp_path / "small.png", (32, 32))

    report = analyze_input_image(image_path)

    assert report["is_too_small"] is True
    assert report["input_quality_status"] == "warning"
    assert "image_too_small_for_best_quality" in report["warnings"]


def test_create_job_writes_input_quality_report(project_root: Path, sample_input_png: Path) -> None:
    manifest = create_job(project_root, sample_input_png)
    report_path = project_root / "jobs" / manifest["job_id"] / "versions" / "v1" / "validation" / "input_quality_report.json"

    report = read_json(report_path)

    assert report_path.exists()
    assert manifest["input_quality_report_path"] == str(report_path)
    assert report["image_path"].endswith("primary_image.png")
    assert "input_quality_status" in report


def test_repair_profiles_generate_profiled_reports(tmp_path: Path, sample_model_glb: Path) -> None:
    output_dir = tmp_path / "engine_output"
    validation_dir = tmp_path / "validation"

    result = run_repair_benchmark(sample_model_glb, output_dir, validation_dir, repair_profile="aggressive_close_holes")

    comparison = read_json(validation_dir / "repair_comparison_report.json")
    light_report = read_json(validation_dir / "repair_report_light.json")
    assert result["repair_profile"] == "aggressive_close_holes"
    assert comparison["repair_profile"] == "aggressive_close_holes"
    assert comparison["no_auto_acceptance"] is True
    assert "aggressive_close_holes_may_close_real_cavities" in comparison["warnings"]
    assert light_report["repair_profile"] == "aggressive_close_holes"
    assert light_report["no_auto_acceptance"] is True
    assert "technical_recommendation" in light_report


def test_import_result_package_records_repair_profile(project_root: Path, sample_input_png: Path, result_package_sample: Path) -> None:
    manifest = create_job(project_root, sample_input_png)

    candidate = import_result_package(project_root, manifest["job_id"], result_package_sample, repair_profile="visual_preserve")

    comparison_path = project_root / "jobs" / manifest["job_id"] / "versions" / "v1" / "validation" / "repair_comparison_report.json"
    comparison = read_json(comparison_path)
    assert candidate["repair_profile"] == "visual_preserve"
    assert comparison["repair_profile"] == "visual_preserve"


def test_repairs_remain_candidates_and_stl_stays_blocked(project_root: Path, sample_input_png: Path, result_package_sample: Path) -> None:
    manifest = create_job(project_root, sample_input_png)
    candidate = import_result_package(project_root, manifest["job_id"], result_package_sample, repair_profile="printability")

    for repaired_path in candidate["repaired_candidate_paths"].values():
        if repaired_path:
            assert Path(repaired_path).name.startswith("repaired_candidate_")
            assert not Path(repaired_path).with_suffix(".stl").exists()
    with pytest.raises(HY3DError, match="active accepted version"):
        export_active_accepted_stl(project_root, manifest["job_id"])


def test_local_connector_passes_selected_repair_profile(tmp_path: Path, sample_input_png: Path, result_package_sample: Path) -> None:
    root = tmp_path / "workspace"
    (root / "jobs").mkdir(parents=True)
    manifest = create_job(root, sample_input_png)
    props = SimpleNamespace(
        job_id=manifest["job_id"],
        version_id="v1",
        repair_profile="printability",
        result_package_path="",
        candidate_model_path="",
        repaired_candidate_path="",
        repaired_candidate_light_path="",
        repaired_candidate_meshfix_path="",
        repaired_candidate_meshlab_path="",
        accepted_model_path="",
        accepted_stl_path="",
        stl_validation_report_path="",
        printability_report_path="",
        input_quality_status="",
        input_quality_warnings="",
        input_quality_report_path="",
        engine_output_dir="",
        local_engine_status_path="",
    )

    import hy3d_local_connector_addon.hy3d_local_connector as connector

    original_workspace_root = connector.workspace_root
    try:
        connector.workspace_root = lambda: root
        _import_result_package_into_session(props, result_package_sample)
    finally:
        connector.workspace_root = original_workspace_root

    comparison = read_json(root / "jobs" / manifest["job_id"] / "versions" / "v1" / "validation" / "repair_comparison_report.json")
    assert comparison["repair_profile"] == "printability"
    assert props.input_quality_report_path.endswith("input_quality_report.json")
