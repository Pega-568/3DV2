from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace


LOCAL_CONNECTOR_ROOT = Path(__file__).resolve().parents[2] / "hy3d_local_connector_addon"
if str(LOCAL_CONNECTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(LOCAL_CONNECTOR_ROOT))

import hy3d_local_connector  # noqa: E402


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
    assert hy3d_local_connector.WRAPPER_RUN == Path(r"E:\3D_ENGINES\wrappers\run_triposr_local.ps1")
    assert hy3d_local_connector.ENGINE_VENV == Path(r"E:\3D_ENGINES\triposr-local\.venv")
    assert hy3d_local_connector.ENGINE_REPO == Path(r"E:\3D_ENGINES\triposr-local\TripoSR")


def test_local_connector_engine_check_detects_real_installation() -> None:
    status = hy3d_local_connector._local_engine_status()
    assert status["wrapper_exists"] is True
    assert status["venv_exists"] is True
    assert status["python_exists"] is True
    assert status["triposr_repo_exists"] is True
    assert status["run_py_exists"] is True
    assert status["sample_input_exists"] is True


def test_local_connector_result_package_validation() -> None:
    path, error = hy3d_local_connector._validate_result_package_path("")
    assert path is None
    assert error == "Result package path is not available."

    valid, valid_error = hy3d_local_connector._validate_result_package_path(
        r"E:\3D_ENGINES\triposr-local\outputs\job_test\result_package.zip"
    )
    assert valid_error is None
    assert valid == Path(r"E:\3D_ENGINES\triposr-local\outputs\job_test\result_package.zip")


def test_local_connector_no_stl_without_accepted() -> None:
    props = SimpleNamespace(job_id="job_test", accepted_model_path="")
    assert hy3d_local_connector._stl_export_ready(props) is False
