from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import pytest

from hy3d_v2.hy3d_core.job_service import (
    HY3DError,
    create_job,
    create_job_package,
    create_new_version_from_accepted,
    export_active_accepted_stl,
    import_result_package,
    promote_edited_model_to_accepted,
    promote_selected_object_to_accepted,
    save_edited_model,
    save_manual_review,
    simulate_copy_exporter,
)
from hy3d_v2.hy3d_core.models import ReferenceView, ReviewPayload
from hy3d_v2.hy3d_core.utils.files import read_json


ASSETS_DIR = Path(__file__).resolve().parents[1] / "test_assets"


def write_ascii_stl(_accepted_glb: Path, stl_path: Path) -> None:
    stl_path.write_text(
        "solid accepted\n"
        "facet normal 0 0 1\n"
        " outer loop\n"
        "  vertex 0 0 0\n"
        "  vertex 1 0 0\n"
        "  vertex 0 1 0\n"
        " endloop\n"
        "endfacet\n"
        "endsolid accepted\n",
        encoding="utf-8",
    )


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


def test_create_job_and_package(project_root: Path, sample_input_png: Path) -> None:
    extra = project_root / "side.png"
    shutil.copy2(sample_input_png, extra)
    manifest = create_job(
        project_root,
        sample_input_png,
        reference_views=[ReferenceView(path=extra, view_type="side")],
        prompt="make it clean",
        input_mode="multiple_views",
    )
    zip_path = create_job_package(project_root, manifest["job_id"])

    assert zip_path.exists()
    with zipfile.ZipFile(zip_path, "r") as archive:
        names = set(archive.namelist())
    assert "job_manifest.json" in names
    assert "input/primary_image.png" in names
    assert "multi_view/multi_view_manifest.json" in names
    assert "instructions/prompt.txt" in names

    job_manifest = read_json(project_root / "jobs" / manifest["job_id"] / "job_manifest.json")
    multi_view = read_json(project_root / "jobs" / manifest["job_id"] / "multi_view" / "multi_view_manifest.json")
    assert job_manifest["active_version"] == "v1"
    assert multi_view["reference_views"][0]["view_type"] == "side"


def test_import_result_package_creates_candidate_manifest(project_root: Path, sample_input_png: Path, result_package_sample: Path) -> None:
    manifest = create_job(project_root, sample_input_png)
    candidate = import_result_package(project_root, manifest["job_id"], result_package_sample)

    assert candidate["version_id"] == "v1"
    candidate_manifest = project_root / "jobs" / manifest["job_id"] / "versions" / "v1" / "engine_output" / "candidate_manifest.json"
    assert candidate_manifest.exists()
    assert (project_root / "jobs" / manifest["job_id"] / "versions" / "v1" / "engine_output" / "model.glb").exists()
    validation_report = read_json(project_root / "jobs" / manifest["job_id"] / "versions" / "v1" / "validation" / "candidate_validation_report.json")
    assert validation_report["file_size"] > 0
    assert "validation_warnings" in validation_report


def test_save_review_and_promote_to_accepted(project_root: Path, sample_input_png: Path, sample_model_glb: Path) -> None:
    manifest = create_job(project_root, sample_input_png)
    review = ReviewPayload(4, 4, 4, "minor", True, "light", "usable candidate")
    review_path = save_manual_review(project_root, manifest["job_id"], "v1", review)
    accepted_path = promote_selected_object_to_accepted(
        project_root,
        manifest["job_id"],
        "v1",
        exporter=simulate_copy_exporter(sample_model_glb),
        accepted_object_name="Candidate",
        source_candidate_path=str(sample_model_glb),
        human_edited=True,
    )

    assert review_path.exists()
    assert accepted_path.exists()
    accepted_manifest = read_json(accepted_path.parent / "accepted_manifest.json")
    assert accepted_manifest["accepted_source"] == "selected_blender_object"


def test_block_stl_without_accepted_model(project_root: Path, sample_input_png: Path) -> None:
    manifest = create_job(project_root, sample_input_png)
    with pytest.raises(HY3DError, match="active accepted version"):
        export_active_accepted_stl(project_root, manifest["job_id"])


def test_export_stl_uses_accepted_model_only(project_root: Path, sample_input_png: Path, sample_model_glb: Path) -> None:
    manifest = create_job(project_root, sample_input_png)
    promote_selected_object_to_accepted(
        project_root,
        manifest["job_id"],
        "v1",
        exporter=simulate_copy_exporter(sample_model_glb),
        accepted_object_name="Accepted",
        source_candidate_path=str(sample_model_glb),
        human_edited=False,
    )
    stl_path = export_active_accepted_stl(project_root, manifest["job_id"], exporter=write_ascii_stl)
    accepted_dir = project_root / "jobs" / manifest["job_id"] / "versions" / "v1" / "accepted"

    assert stl_path == accepted_dir / "accepted_model.stl"
    stl_validation = read_json(accepted_dir / "stl_validation_report.json")
    assert (accepted_dir / "printability_report.json").exists()
    assert "watertight" in stl_validation
    assert "bbox" in stl_validation
    assert "printability_status" in stl_validation


def test_create_second_version_from_active_accepted(project_root: Path, sample_input_png: Path, sample_model_glb: Path) -> None:
    manifest = create_job(project_root, sample_input_png)
    promote_selected_object_to_accepted(
        project_root,
        manifest["job_id"],
        "v1",
        exporter=simulate_copy_exporter(sample_model_glb),
        accepted_object_name="Accepted",
        source_candidate_path=str(sample_model_glb),
        human_edited=False,
    )

    v2 = create_new_version_from_accepted(project_root, manifest["job_id"], "add more detail")

    assert v2["version_id"] == "v2"
    assert (project_root / "jobs" / manifest["job_id"] / "versions" / "v2" / "source" / "source_model.glb").exists()


def test_no_overwrite_same_version_accepted_glb(project_root: Path, sample_input_png: Path, sample_model_glb: Path) -> None:
    manifest = create_job(project_root, sample_input_png)
    promote_selected_object_to_accepted(
        project_root,
        manifest["job_id"],
        "v1",
        exporter=simulate_copy_exporter(sample_model_glb),
        accepted_object_name="Accepted",
        source_candidate_path=str(sample_model_glb),
        human_edited=False,
    )
    with pytest.raises(HY3DError, match="already exists"):
        promote_selected_object_to_accepted(
            project_root,
            manifest["job_id"],
            "v1",
            exporter=simulate_copy_exporter(sample_model_glb),
            accepted_object_name="Accepted",
            source_candidate_path=str(sample_model_glb),
            human_edited=False,
        )


def test_model_glb_does_not_create_stl_without_accepted(project_root: Path, sample_input_png: Path, result_package_sample: Path) -> None:
    manifest = create_job(project_root, sample_input_png)
    import_result_package(project_root, manifest["job_id"], result_package_sample)
    accepted_dir = project_root / "jobs" / manifest["job_id"] / "versions" / "v1" / "accepted"

    assert not (accepted_dir / "accepted_model.stl").exists()
    with pytest.raises(HY3DError, match="active accepted version"):
        export_active_accepted_stl(project_root, manifest["job_id"])


def test_save_edited_model_and_promote_from_edited(project_root: Path, sample_input_png: Path, sample_model_glb: Path) -> None:
    manifest = create_job(project_root, sample_input_png)
    edited_path = save_edited_model(
        project_root,
        manifest["job_id"],
        "v1",
        exporter=simulate_copy_exporter(sample_model_glb),
        edited_object_name="EditedCube",
        source_candidate_path=str(sample_model_glb),
    )
    accepted_path = promote_edited_model_to_accepted(
        project_root,
        manifest["job_id"],
        "v1",
        source_edited_model=edited_path,
        accepted_object_name="EditedCube",
        source_candidate_path=str(sample_model_glb),
        human_edited=True,
    )

    edited_manifest = read_json(project_root / "jobs" / manifest["job_id"] / "versions" / "v1" / "edited" / "edited_manifest.json")
    accepted_manifest = read_json(accepted_path.parent / "accepted_manifest.json")
    assert edited_manifest["edited_model_path"].endswith("edited_model.glb")
    assert accepted_manifest["source_type"] == "edited_model"
    assert accepted_manifest["accepted_source"] == "edited_model_glb"


def test_import_result_package_rejects_missing_result_manifest(project_root: Path, sample_input_png: Path, tmp_path: Path, sample_model_glb: Path) -> None:
    manifest = create_job(project_root, sample_input_png)
    bad_zip = tmp_path / "missing_manifest.zip"
    with zipfile.ZipFile(bad_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(sample_model_glb, "model.glb")
    with pytest.raises(HY3DError, match="missing result_manifest.json"):
        import_result_package(project_root, manifest["job_id"], bad_zip)


def test_import_result_package_rejects_unsafe_zip_paths(project_root: Path, sample_input_png: Path, tmp_path: Path, sample_model_glb: Path) -> None:
    manifest = create_job(project_root, sample_input_png)
    bad_zip = tmp_path / "unsafe_paths.zip"
    with zipfile.ZipFile(bad_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("result_manifest.json", '{"result_package_version": 1}')
        archive.write(sample_model_glb, "../model.glb")
    with pytest.raises(HY3DError, match="Unsafe ZIP entry rejected"):
        import_result_package(project_root, manifest["job_id"], bad_zip)
