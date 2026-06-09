from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

from hy3d_v2.hy3d_core.job_service import create_job, export_active_accepted_stl, promote_selected_object_to_accepted, simulate_copy_exporter


LOCAL_CONNECTOR_ROOT = Path(__file__).resolve().parents[2] / "hy3d_local_connector_addon"
if str(LOCAL_CONNECTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(LOCAL_CONNECTOR_ROOT))

import hy3d_local_connector  # noqa: E402

ASSETS_DIR = Path(__file__).resolve().parents[1] / "test_assets"


def test_local_connector_has_unique_bl_info_and_build_id() -> None:
    assert hy3d_local_connector.bl_info["name"] == "HY3D Local Connector"
    assert hy3d_local_connector.bl_info["location"] == "View3D > Sidebar > HY3D Local Connector"
    assert re.fullmatch(r"hy3d_local_connector_\d{8}_\d{4}", hy3d_local_connector.ADDON_BUILD_ID)


def test_local_connector_operator_ids_are_local_only() -> None:
    source = (LOCAL_CONNECTOR_ROOT / "hy3d_local_connector" / "__init__.py").read_text(encoding="utf-8")
    operator_ids = re.findall(r'bl_idname = "([^"]+)"', source)
    assert operator_ids
    assert len(operator_ids) == len(set(operator_ids))
    assert all(op.startswith("hy3d_local_connector.") or op == "HY3D_LOCAL_CONNECTOR_PT_main_panel" for op in operator_ids)


def test_local_connector_has_no_legacy_ids() -> None:
    source = (LOCAL_CONNECTOR_ROOT / "hy3d_local_connector" / "__init__.py").read_text(encoding="utf-8")
    forbidden = [
        'bl_idname = "hy3d_v2.',
        'bl_idname = "hy3d_v2_clean.',
        "HY3D_PT_main_panel",
        "prefer_3d_if_safe",
        "Relief",
        "7A",
        "7B",
        "7C",
        "Cloud",
        "Colab",
        "Drive",
    ]
    for item in forbidden:
        assert item not in source


def test_local_connector_wrapper_paths_are_expected() -> None:
    assert hy3d_local_connector.PROJECT_ROOT == Path(__file__).resolve().parents[1]
    assert hy3d_local_connector.WRAPPER_RUN == hy3d_local_connector.ENGINE_ROOT.parent / "wrappers" / "run_triposr_local.ps1"
    assert hy3d_local_connector.ENGINE_VENV == hy3d_local_connector.ENGINE_ROOT / ".venv"
    assert hy3d_local_connector.ENGINE_REPO == hy3d_local_connector.ENGINE_ROOT / "TripoSR"


def test_local_connector_engine_check_detects_real_installation() -> None:
    status = hy3d_local_connector._local_engine_status()
    assert isinstance(status["wrapper_exists"], bool)
    assert isinstance(status["venv_exists"], bool)
    assert isinstance(status["python_exists"], bool)
    assert isinstance(status["triposr_repo_exists"], bool)
    assert isinstance(status["run_py_exists"], bool)
    assert status["sample_input_exists"] is True
    assert status["project_root"] == str(hy3d_local_connector.PROJECT_ROOT)
    assert status["engine_root"] == str(hy3d_local_connector.ENGINE_ROOT)


def test_local_connector_open_folder_helpers_return_valid_paths(tmp_path: Path) -> None:
    engine_output_dir = tmp_path / "outputs" / "job_test"
    engine_output_dir.mkdir(parents=True)
    props = SimpleNamespace(
        engine_output_dir=str(engine_output_dir),
        exports_dir="",
        job_id="",
        version_id="v1",
    )
    assert hy3d_local_connector._path_openable(hy3d_local_connector._engine_output_dir_path(props)) is True


def test_local_connector_result_package_validation(tmp_path: Path) -> None:
    path, error = hy3d_local_connector._validate_result_package_path("")
    assert path is None
    assert error == "Result package path is not available."

    result_package = tmp_path / "result_package.zip"
    result_package.write_text("zip-placeholder", encoding="utf-8")
    valid, valid_error = hy3d_local_connector._validate_result_package_path(result_package)
    assert valid_error is None
    assert valid == result_package


def test_local_connector_repaired_candidate_helper_rejects_empty() -> None:
    props = SimpleNamespace(
        repaired_candidate_path="",
        repaired_candidate_light_path="",
        repaired_candidate_meshfix_path="",
        repaired_candidate_meshlab_path="",
    )
    assert hy3d_local_connector._has_valid_repaired_candidate_path(props) is False
    assert hy3d_local_connector._has_valid_light_candidate_path(props) is False
    assert hy3d_local_connector._has_valid_meshfix_candidate_path(props) is False
    assert hy3d_local_connector._has_valid_meshlab_candidate_path(props) is False


def test_local_connector_no_stl_without_accepted() -> None:
    props = SimpleNamespace(job_id="job_test", accepted_model_path="")
    assert hy3d_local_connector._stl_export_ready(props) is False


def test_local_connector_engine_generated_state_writes_status(tmp_path: Path) -> None:
    props = SimpleNamespace(
        engine_job_id="",
        engine_output_dir="",
        result_package_path="",
        hy3d_imported=False,
        job_id="",
        candidate_model_path="",
        repaired_candidate_path="",
        repaired_candidate_light_path="",
        repaired_candidate_meshfix_path="",
        repaired_candidate_meshlab_path="",
        accepted_model_path="",
        accepted_stl_path="",
        stl_validation_report_path="",
        printability_report_path="",
        exports_dir="",
        current_status=hy3d_local_connector.STATUS_NO_JOB,
        local_engine_status_path="",
        last_status="",
        last_error="",
    )
    engine_output_dir = tmp_path / "job_fake"
    engine_output_dir.mkdir(parents=True)
    result_package = engine_output_dir / "result_package.zip"
    result_package.write_text("zip-placeholder", encoding="utf-8")

    hy3d_local_connector._set_engine_generated_state(props, "job_fake", engine_output_dir, result_package)

    assert props.current_status == hy3d_local_connector.STATUS_ENGINE_GENERATED
    status_path = engine_output_dir / "local_engine_status.json"
    assert status_path.exists()
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["status"] == hy3d_local_connector.STATUS_ENGINE_GENERATED
    assert payload["hy3d_imported"] is False
    assert payload["result_package_path"] == str(result_package)


def test_local_connector_validate_stl_not_ready_without_files() -> None:
    props = SimpleNamespace(job_id="job_test", version_id="v1", accepted_model_path="")
    assert hy3d_local_connector._validate_stl_ready(props) is False


def test_local_connector_validate_existing_stl_writes_reports(tmp_path: Path) -> None:
    root = tmp_path / "hy3d_local_connector_workspace"
    (root / "jobs").mkdir(parents=True)
    sample_input = tmp_path / "sample_input.png"
    sample_model = tmp_path / "sample_model.glb"
    shutil.copy2(ASSETS_DIR / "sample_input.png", sample_input)
    shutil.copy2(ASSETS_DIR / "sample_model.glb", sample_model)
    manifest = create_job(root, sample_input)
    accepted_path = promote_selected_object_to_accepted(
        root,
        manifest["job_id"],
        "v1",
        exporter=simulate_copy_exporter(sample_model),
        accepted_object_name="Accepted",
        source_candidate_path=str(sample_model),
        human_edited=True,
    )
    export_active_accepted_stl(root, manifest["job_id"], exporter=lambda _glb, stl: stl.write_text("solid x\nendsolid x\n", encoding="utf-8"))
    props = SimpleNamespace(job_id=manifest["job_id"], version_id="v1", accepted_model_path=str(accepted_path))

    original_workspace_root = hy3d_local_connector.workspace_root
    try:
        hy3d_local_connector.workspace_root = lambda: root
        report = hy3d_local_connector._validate_existing_stl(props)
    finally:
        hy3d_local_connector.workspace_root = original_workspace_root

    accepted_dir = root / "jobs" / manifest["job_id"] / "versions" / "v1" / "accepted"
    assert (accepted_dir / "stl_validation_report.json").exists()
    assert (accepted_dir / "printability_report.json").exists()
    assert report["exists"] is True
    assert "file_size" in report
    assert "readable" in report


def test_local_connector_import_result_session_sets_repaired_candidate(tmp_path: Path) -> None:
    root = tmp_path / "hy3d_local_connector_workspace"
    (root / "jobs").mkdir(parents=True)
    sample_input = tmp_path / "sample_input.png"
    shutil.copy2(ASSETS_DIR / "sample_input.png", sample_input)
    manifest = create_job(root, sample_input)
    props = SimpleNamespace(
        job_id=manifest["job_id"],
        version_id="v1",
        result_package_path="",
        candidate_model_path="",
        repaired_candidate_path="",
        repaired_candidate_light_path="",
        repaired_candidate_meshfix_path="",
        repaired_candidate_meshlab_path="",
        accepted_model_path="",
        accepted_stl_path="",
    )

    original_workspace_root = hy3d_local_connector.workspace_root
    try:
        hy3d_local_connector.workspace_root = lambda: root
        hy3d_local_connector._import_result_package_into_session(
            props,
            ASSETS_DIR / "result_package_sample.zip",
        )
    finally:
        hy3d_local_connector.workspace_root = original_workspace_root

    assert props.candidate_model_path.endswith("model.glb")
    assert hasattr(props, "repaired_candidate_path")
    assert hasattr(props, "repaired_candidate_light_path")
    assert hasattr(props, "repaired_candidate_meshfix_path")
    assert hasattr(props, "repaired_candidate_meshlab_path")


def test_local_connector_import_existing_result_package_flow_updates_status(tmp_path: Path) -> None:
    root = tmp_path / "hy3d_local_connector_workspace"
    (root / "jobs").mkdir(parents=True)
    engine_output_dir = tmp_path / "job_test"
    (engine_output_dir / "engine_raw" / "0").mkdir(parents=True)
    sample_input = engine_output_dir / "engine_raw" / "0" / "input.png"
    shutil.copy2(ASSETS_DIR / "sample_input.png", sample_input)
    result_package = engine_output_dir / "result_package.zip"
    shutil.copy2(ASSETS_DIR / "result_package_sample.zip", result_package)
    props = SimpleNamespace(
        primary_image_path="",
        engine_job_id="job_test",
        job_id="",
        version_id="v1",
        engine_output_dir=str(engine_output_dir),
        local_engine_status_path="",
        result_package_path=str(result_package),
        candidate_model_path="",
        repaired_candidate_path="",
        repaired_candidate_light_path="",
        repaired_candidate_meshfix_path="",
        repaired_candidate_meshlab_path="",
        accepted_model_path="",
        accepted_stl_path="",
        stl_validation_report_path="",
        printability_report_path="",
        exports_dir="",
        current_status=hy3d_local_connector.STATUS_ENGINE_GENERATED,
        hy3d_imported=False,
        last_status="",
        last_error="",
    )

    original_workspace_root = hy3d_local_connector.workspace_root
    try:
        hy3d_local_connector.workspace_root = lambda: root
        manifest = hy3d_local_connector._import_result_package_from_path(
            props,
            result_package,
        )
    finally:
        hy3d_local_connector.workspace_root = original_workspace_root

    assert manifest["candidate_path"].endswith("model.glb")
    assert props.current_status == hy3d_local_connector.STATUS_IMPORTED_TO_HY3D
    assert props.hy3d_imported is True
    assert props.job_id.startswith("job_")
    status_path = engine_output_dir / "local_engine_status.json"
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["status"] == hy3d_local_connector.STATUS_IMPORTED_TO_HY3D
    assert payload["hy3d_imported"] is True
    assert payload["hy3d_job_id"] == props.job_id


def test_local_connector_exports_folder_receives_copies(tmp_path: Path) -> None:
    root = tmp_path / "hy3d_local_connector_workspace"
    (root / "jobs").mkdir(parents=True)
    sample_input = tmp_path / "sample_input.png"
    sample_model = tmp_path / "sample_model.glb"
    shutil.copy2(ASSETS_DIR / "sample_input.png", sample_input)
    shutil.copy2(ASSETS_DIR / "sample_model.glb", sample_model)
    manifest = create_job(root, sample_input)
    accepted_path = promote_selected_object_to_accepted(
        root,
        manifest["job_id"],
        "v1",
        exporter=simulate_copy_exporter(sample_model),
        accepted_object_name="Accepted",
        source_candidate_path=str(sample_model),
        human_edited=True,
    )
    stl_path = export_active_accepted_stl(root, manifest["job_id"], exporter=lambda _glb, stl: stl.write_text("solid x\nendsolid x\n", encoding="utf-8"))
    accepted_dir = root / "jobs" / manifest["job_id"] / "versions" / "v1" / "accepted"
    (accepted_dir / "stl_validation_report.json").write_text("{}", encoding="utf-8")
    (accepted_dir / "printability_report.json").write_text("{}", encoding="utf-8")
    props = SimpleNamespace(
        engine_job_id="job_exporttest",
        job_id=manifest["job_id"],
        version_id="v1",
        accepted_model_path=str(accepted_path),
        accepted_stl_path=str(stl_path),
        exports_dir="",
    )

    original_exports_root = hy3d_local_connector.EXPORTS_ROOT
    try:
        hy3d_local_connector.EXPORTS_ROOT = tmp_path / "HY3D_EXPORTS"
        export_dir = hy3d_local_connector._sync_exports_from_accepted(props)
    finally:
        hy3d_local_connector.EXPORTS_ROOT = original_exports_root

    assert export_dir == tmp_path / "HY3D_EXPORTS" / "job_exporttest"
    assert (export_dir / "accepted_model.stl").exists()
    assert (export_dir / "accepted_model.glb").exists()
    assert (export_dir / "stl_validation_report.json").exists()
    assert (export_dir / "printability_report.json").exists()
