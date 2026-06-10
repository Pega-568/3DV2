from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parent
ADDON_ROOT = MODULE_ROOT.parent
REPO_ROOT = ADDON_ROOT.parent
LOCAL_CONFIG_PATH = REPO_ROOT / "hy3d_local_config.json"


def _load_local_config() -> dict[str, str]:
    if not LOCAL_CONFIG_PATH.exists():
        return {}
    try:
        payload = json.loads(LOCAL_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value) for key, value in payload.items() if value}


_LOCAL_CONFIG = _load_local_config()


def _configured_path(env_name: str, config_key: str, fallback: Path) -> Path:
    value = os.environ.get(env_name) or _LOCAL_CONFIG.get(config_key) or _LOCAL_CONFIG.get(env_name)
    if value:
        return Path(value).expanduser()
    return fallback


PROJECT_ROOT = _configured_path("HY3D_PROJECT_ROOT", "project_root", REPO_ROOT / "hy3d_v2")
CORE_ROOT = PROJECT_ROOT / "hy3d_core"
LOCAL_CONNECTOR_ROOT = MODULE_ROOT
ENGINE_ROOT = _configured_path("HY3D_ENGINE_ROOT", "engine_root", REPO_ROOT.parent / "3D_ENGINES" / "triposr-local")
WRAPPER_RUN = _configured_path("HY3D_WRAPPER_RUN", "wrapper_run", ENGINE_ROOT.parent / "wrappers" / "run_triposr_local.ps1")
ENGINE_VENV = ENGINE_ROOT / ".venv"
ENGINE_REPO = ENGINE_ROOT / "TripoSR"
EXPORTS_ROOT = _configured_path("HY3D_EXPORTS_ROOT", "exports_root", REPO_ROOT / "HY3D_EXPORTS")
SAMPLE_INPUT = PROJECT_ROOT / "test_assets" / "real_smoke_input.png"
VALID_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".avif"}
ADDON_BUILD_ID = f"hy3d_local_connector_{datetime.now().strftime('%Y%m%d_%H%M')}"
STATUS_NO_JOB = "no_job"
STATUS_ENGINE_GENERATED = "engine_generated"
STATUS_IMPORTED_TO_HY3D = "imported_to_hy3d"
STATUS_CANDIDATE_IMPORTED = "candidate_imported"
STATUS_ACCEPTED = "accepted"
STATUS_STL_EXPORTED = "stl_exported"
STATUS_STL_VALIDATED = "stl_validated"

PROJECT_PARENT = PROJECT_ROOT.parent
if str(PROJECT_PARENT) not in sys.path:
    sys.path.insert(0, str(PROJECT_PARENT))

from hy3d_v2.hy3d_core.job_service import (  # noqa: E402
    HY3DError,
    build_job_paths,
    create_job,
    export_stl_from_accepted,
    import_result_package,
    promote_selected_object_to_accepted,
    save_manual_review,
)
from hy3d_v2.hy3d_core.input_quality.service import analyze_input_image  # noqa: E402
from hy3d_v2.hy3d_core.models import ReviewPayload  # noqa: E402
from hy3d_v2.hy3d_core.stl.service import validate_stl_file  # noqa: E402
from hy3d_v2.hy3d_core.utils.files import read_json, utc_now_iso, write_json  # noqa: E402

bl_info = {
    "name": "HY3D Local Connector",
    "author": "OpenAI Codex",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > HY3D Local Connector",
    "description": "Minimal local TripoSR connector for HY3D",
    "category": "3D View",
}

try:  # pragma: no cover - Blender-only import
    import bpy
    from bpy.props import BoolProperty, IntProperty, PointerProperty, StringProperty
    from bpy.types import Operator, Panel, PropertyGroup
    from bpy_extras.io_utils import ImportHelper

    BLENDER_AVAILABLE = True
except Exception:  # pragma: no cover - importable outside Blender for tests
    bpy = None
    BLENDER_AVAILABLE = False

    class Operator:  # type: ignore[override]
        pass

    class Panel:  # type: ignore[override]
        pass

    class PropertyGroup:  # type: ignore[override]
        pass

    class ImportHelper:  # type: ignore[override]
        pass

    def StringProperty(**_kwargs):  # type: ignore[misc]
        return None

    def IntProperty(**_kwargs):  # type: ignore[misc]
        return None

    def BoolProperty(**_kwargs):  # type: ignore[misc]
        return None

    def PointerProperty(**_kwargs):  # type: ignore[misc]
        return None


def workspace_root() -> Path:
    if BLENDER_AVAILABLE:
        base = Path(bpy.utils.user_resource("DATAFILES", path="hy3d_local_connector_workspace", create=True))
        base.mkdir(parents=True, exist_ok=True)
        return base
    fallback = PROJECT_ROOT.parent / "hy3d_local_connector_workspace"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _new_engine_job_id() -> str:
    return f"job_{uuid.uuid4().hex[:12]}"


def _normalize_path_string(raw_value) -> str:
    if raw_value is None:
        return ""
    raw = str(raw_value).strip().strip('"').strip("'")
    if BLENDER_AVAILABLE and raw:
        try:
            raw = bpy.path.abspath(raw)
        except Exception:
            pass
    return raw


def _resolve_existing_file(value, suffix: str | None = None) -> Path | None:
    raw = _normalize_path_string(value)
    if not raw or raw == ".":
        return None
    path = Path(raw)
    if not path.exists() or not path.is_file():
        return None
    if suffix and path.suffix.lower() != suffix.lower():
        return None
    return path


def _resolve_existing_dir(value) -> Path | None:
    raw = _normalize_path_string(value)
    if not raw or raw == ".":
        return None
    path = Path(raw)
    if not path.exists() or not path.is_dir():
        return None
    return path


def _validate_primary_image(value) -> tuple[Path | None, str | None]:
    raw = _normalize_path_string(value)
    if not raw:
        return None, "Please select a primary image before running Local TripoSR."
    if raw == ".":
        return None, "Invalid primary image path."
    path = Path(raw)
    if not path.exists():
        return None, "Primary image file does not exist."
    if not path.is_file():
        return None, "Primary image path is not a file."
    if path.suffix.lower() not in VALID_IMAGE_SUFFIXES:
        return None, "Unsupported image format."
    return path, None


def _validate_result_package_path(value) -> tuple[Path | None, str | None]:
    raw = _normalize_path_string(value)
    if not raw:
        return None, "Result package path is not available."
    if raw == ".":
        return None, "Invalid result package path."
    path = Path(raw)
    if not path.exists() or not path.is_file() or path.suffix.lower() != ".zip":
        return None, "Result package path must be a valid .zip file."
    return path, None


def _engine_output_dir_path(props) -> Path | None:
    return _resolve_existing_dir(getattr(props, "engine_output_dir", ""))


def _hy3d_job_dir_path(props) -> Path | None:
    job_id = getattr(props, "job_id", "").strip()
    if not job_id:
        return None
    return _resolve_existing_dir(workspace_root() / "jobs" / job_id)


def _accepted_dir_path(props) -> Path | None:
    accepted_model = _resolve_existing_file(getattr(props, "accepted_model_path", ""), suffix=".glb")
    if accepted_model is not None:
        return _resolve_existing_dir(accepted_model.parent)
    job_dir = _hy3d_job_dir_path(props)
    if job_dir is None:
        return None
    version_id = getattr(props, "version_id", "v1") or "v1"
    return _resolve_existing_dir(job_dir / "versions" / version_id / "accepted")


def _validation_dir_path(props) -> Path | None:
    job_dir = _hy3d_job_dir_path(props)
    if job_dir is None:
        return None
    version_id = getattr(props, "version_id", "v1") or "v1"
    return _resolve_existing_dir(job_dir / "versions" / version_id / "validation")


def _exports_dir_path(props) -> Path | None:
    return _resolve_existing_dir(getattr(props, "exports_dir", ""))


def _has_valid_candidate_model_path(props) -> bool:
    return _resolve_existing_file(getattr(props, "candidate_model_path", ""), suffix=".glb") is not None


def _has_valid_repaired_candidate_path(props) -> bool:
    return _resolve_existing_file(getattr(props, "repaired_candidate_path", ""), suffix=".glb") is not None


def _has_valid_light_candidate_path(props) -> bool:
    return _resolve_existing_file(getattr(props, "repaired_candidate_light_path", ""), suffix=".glb") is not None


def _has_valid_meshfix_candidate_path(props) -> bool:
    return _resolve_existing_file(getattr(props, "repaired_candidate_meshfix_path", ""), suffix=".glb") is not None


def _has_valid_meshlab_candidate_path(props) -> bool:
    return _resolve_existing_file(getattr(props, "repaired_candidate_meshlab_path", ""), suffix=".glb") is not None


def _has_valid_accepted_model_path(props) -> bool:
    return _resolve_existing_file(getattr(props, "accepted_model_path", ""), suffix=".glb") is not None


def _stl_export_ready(props) -> bool:
    return getattr(props, "current_status", STATUS_NO_JOB) == STATUS_ACCEPTED and _has_valid_accepted_model_path(props)


def _validate_stl_ready(props) -> bool:
    if getattr(props, "current_status", STATUS_NO_JOB) not in {STATUS_STL_EXPORTED, STATUS_STL_VALIDATED}:
        return False
    if not bool(getattr(props, "job_id", "").strip()):
        return False
    accepted_model = _resolve_existing_file(getattr(props, "accepted_model_path", ""), suffix=".glb")
    if accepted_model is None:
        return False
    stl_path = build_job_paths(workspace_root(), props.job_id, getattr(props, "version_id", "v1") or "v1").accepted_dir / "accepted_model.stl"
    return stl_path.exists() and stl_path.is_file()


def _local_engine_status() -> dict[str, object]:
    python_exe = ENGINE_VENV / "Scripts" / "python.exe"
    run_py = ENGINE_REPO / "run.py"
    return {
        "build_id": ADDON_BUILD_ID,
        "addon_path": str(LOCAL_CONNECTOR_ROOT),
        "config_path": str(LOCAL_CONFIG_PATH),
        "config_exists": LOCAL_CONFIG_PATH.exists(),
        "project_root": str(PROJECT_ROOT),
        "workspace": str(workspace_root()),
        "engine_root": str(ENGINE_ROOT),
        "wrapper_run": str(WRAPPER_RUN),
        "exports_root": str(EXPORTS_ROOT),
        "wrapper_exists": WRAPPER_RUN.exists(),
        "venv_exists": ENGINE_VENV.exists(),
        "python_exists": python_exe.exists(),
        "triposr_repo_exists": ENGINE_REPO.exists(),
        "run_py_exists": run_py.exists(),
        "sample_input_exists": SAMPLE_INPUT.exists(),
    }


def _status_payload(props) -> dict[str, object]:
    return {
        "allowed_statuses": [
            STATUS_NO_JOB,
            STATUS_ENGINE_GENERATED,
            STATUS_IMPORTED_TO_HY3D,
            STATUS_CANDIDATE_IMPORTED,
            STATUS_ACCEPTED,
            STATUS_STL_EXPORTED,
            STATUS_STL_VALIDATED,
        ],
        "engine_job_id": getattr(props, "engine_job_id", "").strip() or None,
        "engine_output_dir": _normalize_path_string(getattr(props, "engine_output_dir", "")) or None,
        "result_package_path": _normalize_path_string(getattr(props, "result_package_path", "")) or None,
        "hy3d_imported": bool(getattr(props, "hy3d_imported", False)),
        "hy3d_job_id": getattr(props, "job_id", "").strip() or None,
        "hy3d_job_folder": str(_hy3d_job_dir_path(props)) if _hy3d_job_dir_path(props) else None,
        "accepted_model_path": _normalize_path_string(getattr(props, "accepted_model_path", "")) or None,
        "repaired_candidate_light_path": _normalize_path_string(getattr(props, "repaired_candidate_light_path", "")) or None,
        "repaired_candidate_meshfix_path": _normalize_path_string(getattr(props, "repaired_candidate_meshfix_path", "")) or None,
        "repaired_candidate_meshlab_path": _normalize_path_string(getattr(props, "repaired_candidate_meshlab_path", "")) or None,
        "stl_path": _normalize_path_string(getattr(props, "accepted_stl_path", "")) or None,
        "stl_validation_report_path": _normalize_path_string(getattr(props, "stl_validation_report_path", "")) or None,
        "printability_report_path": _normalize_path_string(getattr(props, "printability_report_path", "")) or None,
        "exports_folder": _normalize_path_string(getattr(props, "exports_dir", "")) or None,
        "input_quality_status": str(getattr(props, "input_quality_status", "") or ""),
        "input_quality_warnings": str(getattr(props, "input_quality_warnings", "") or ""),
        "repair_profile": str(getattr(props, "repair_profile", "safe_light") or "safe_light"),
        "status": getattr(props, "current_status", STATUS_NO_JOB),
    }


def _local_engine_status_file_path(props) -> Path | None:
    engine_output_dir = _engine_output_dir_path(props)
    if engine_output_dir is None:
        return None
    return engine_output_dir / "local_engine_status.json"


def _write_local_engine_status(props) -> Path | None:
    status_path = _local_engine_status_file_path(props)
    if status_path is None:
        return None
    write_json(status_path, _status_payload(props))
    props.local_engine_status_path = str(status_path)
    return status_path


def _set_status(props, status: str) -> None:
    props.current_status = status
    _write_local_engine_status(props)


def _set_engine_generated_state(props, engine_job_id: str, engine_output_dir: Path, result_package_path: Path) -> None:
    props.engine_job_id = engine_job_id
    props.engine_output_dir = str(engine_output_dir)
    props.result_package_path = str(result_package_path)
    props.hy3d_imported = False
    props.job_id = ""
    props.candidate_model_path = ""
    props.repaired_candidate_path = ""
    props.repaired_candidate_light_path = ""
    props.repaired_candidate_meshfix_path = ""
    props.repaired_candidate_meshlab_path = ""
    props.accepted_model_path = ""
    props.accepted_stl_path = ""
    props.stl_validation_report_path = ""
    props.printability_report_path = ""
    props.exports_dir = ""
    props.last_status = STATUS_ENGINE_GENERATED
    props.last_error = ""
    _set_status(props, STATUS_ENGINE_GENERATED)


def _set_imported_to_hy3d_state(props, hy3d_job_id: str) -> None:
    props.job_id = hy3d_job_id
    props.hy3d_imported = True
    props.last_status = STATUS_IMPORTED_TO_HY3D
    props.last_error = ""
    _set_status(props, STATUS_IMPORTED_TO_HY3D)


def _exports_job_dir(engine_job_id: str) -> Path:
    target_name = engine_job_id if engine_job_id.startswith("job_") else f"job_{engine_job_id}"
    target = EXPORTS_ROOT / target_name
    target.mkdir(parents=True, exist_ok=True)
    return target


def _sync_exports_from_accepted(props) -> Path:
    accepted_model = _resolve_existing_file(getattr(props, "accepted_model_path", ""), suffix=".glb")
    accepted_stl = _resolve_existing_file(getattr(props, "accepted_stl_path", ""), suffix=".stl")
    if accepted_model is None or accepted_stl is None:
        raise HY3DError("Accepted GLB and STL are required before exporting to HY3D_EXPORTS.")
    accepted_dir = _accepted_dir_path(props)
    if accepted_dir is None:
        raise HY3DError("Accepted folder is not available.")
    engine_job_id = getattr(props, "engine_job_id", "").strip()
    if not engine_job_id:
        engine_job_id = getattr(props, "job_id", "").strip()
    if not engine_job_id:
        raise HY3DError("Job id is not available.")
    export_dir = _exports_job_dir(engine_job_id)
    for name in [
        "accepted_model.stl",
        "accepted_model.glb",
        "stl_validation_report.json",
        "printability_report.json",
    ]:
        source = accepted_dir / name
        if source.exists() and source.is_file():
            shutil.copy2(source, export_dir / name)
    props.exports_dir = str(export_dir)
    return export_dir


def _resolve_import_primary_image(props, package_path: Path) -> tuple[Path | None, str | None]:
    primary_image, _ = _validate_primary_image(getattr(props, "primary_image_path", ""))
    if primary_image is not None:
        return primary_image, None
    engine_output_dir = package_path.parent
    fallback = engine_output_dir / "engine_raw" / "0" / "input.png"
    if fallback.exists() and fallback.is_file():
        props.primary_image_path = str(fallback)
        return fallback, None
    return None, "Primary image is required to create the HY3D workspace job."


def _import_result_package_from_path(props, package_path: Path) -> dict:
    primary_image, error = _resolve_import_primary_image(props, package_path)
    if primary_image is None:
        raise HY3DError(error or "Primary image is not available.")
    if _engine_output_dir_path(props) is None:
        props.engine_output_dir = str(package_path.parent)
    if not getattr(props, "engine_job_id", "").strip():
        props.engine_job_id = package_path.parent.name
    manifest = create_job(workspace_root(), primary_image)
    _load_input_quality_into_props(props, manifest["job_id"], "v1")
    props.version_id = "v1"
    _set_imported_to_hy3d_state(props, manifest["job_id"])
    imported_manifest = _import_result_package_into_session(props, package_path)
    return imported_manifest


def _reset_session(props) -> None:
    props.primary_image_path = ""
    props.engine_job_id = ""
    props.job_id = ""
    props.version_id = "v1"
    props.engine_output_dir = ""
    props.local_engine_status_path = ""
    props.result_package_path = ""
    props.candidate_model_path = ""
    props.repaired_candidate_path = ""
    props.repaired_candidate_light_path = ""
    props.repaired_candidate_meshfix_path = ""
    props.repaired_candidate_meshlab_path = ""
    props.accepted_model_path = ""
    props.accepted_stl_path = ""
    props.stl_validation_report_path = ""
    props.printability_report_path = ""
    props.exports_dir = ""
    props.input_quality_status = ""
    props.input_quality_warnings = ""
    props.input_quality_report_path = ""
    props.hy3d_imported = False
    props.current_status = STATUS_NO_JOB
    props.self_check_status = ""
    props.last_status = STATUS_NO_JOB
    props.last_error = ""


def _find_imported_object(job_id: str, role: str):
    if not BLENDER_AVAILABLE:
        return None
    for obj in bpy.data.objects:
        if obj.get("hy3d_job_id") == job_id and obj.get("hy3d_role") == role:
            return obj
    return None


def _is_hy3d_scene_object(obj) -> bool:
    try:
        return bool(obj.get("hy3d_job_id") and obj.get("hy3d_role") in {"candidate", "accepted"})
    except Exception:
        return False


def _input_quality_summary(image_path: Path) -> tuple[str, str]:
    report = analyze_input_image(image_path)
    return str(report.get("input_quality_status") or "unknown"), ", ".join(report.get("warnings", []))


def _load_input_quality_into_props(props, job_id: str, version_id: str) -> None:
    report_path = build_job_paths(workspace_root(), job_id, version_id).manifests["input_quality"]
    props.input_quality_report_path = str(report_path)
    if not report_path.exists():
        return
    try:
        report = read_json(report_path)
    except Exception:
        return
    props.input_quality_status = str(report.get("input_quality_status") or "")
    props.input_quality_warnings = ", ".join(report.get("warnings", []))


def _import_result_package_into_session(props, package_path: Path) -> dict:
    manifest = import_result_package(
        workspace_root(),
        props.job_id,
        package_path,
        version_id=props.version_id or "v1",
        repair_profile=getattr(props, "repair_profile", "safe_light") or "safe_light",
    )
    props.result_package_path = str(package_path)
    props.candidate_model_path = manifest["candidate_path"]
    props.repaired_candidate_path = str(manifest.get("repaired_candidate_path") or "")
    props.repaired_candidate_light_path = str(manifest.get("repaired_candidate_light_path") or "")
    props.repaired_candidate_meshfix_path = str(manifest.get("repaired_candidate_meshfix_path") or "")
    props.repaired_candidate_meshlab_path = str(manifest.get("repaired_candidate_meshlab_path") or "")
    props.accepted_model_path = ""
    props.accepted_stl_path = ""
    props.stl_validation_report_path = ""
    props.printability_report_path = ""
    _load_input_quality_into_props(props, props.job_id, props.version_id or "v1")
    _write_local_engine_status(props)
    return manifest


def _import_candidate_glb_for_review(context, props, candidate_path: Path, candidate_type: str, label: str) -> None:
    existing_names = {obj.name for obj in bpy.data.objects}
    bpy.ops.import_scene.gltf(filepath=str(candidate_path))
    imported = [obj for obj in context.selected_objects if obj.name not in existing_names] or list(context.selected_objects)
    for obj in imported:
        obj["hy3d_role"] = "candidate"
        obj["hy3d_candidate_type"] = candidate_type
        obj["hy3d_source_path"] = str(candidate_path)
        obj["hy3d_job_id"] = props.job_id
    _set_status(props, STATUS_CANDIDATE_IMPORTED)


def _export_selected_object_to_stl(stl_path: Path, accepted_object) -> None:
    stl_path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(bpy.ops.wm, "stl_export"):
        with bpy.context.temp_override(
            active_object=accepted_object,
            object=accepted_object,
            selected_objects=[accepted_object],
            selected_editable_objects=[accepted_object],
        ):
            bpy.ops.wm.stl_export(filepath=str(stl_path), export_selected_objects=True, check_existing=False)
        return
    if hasattr(bpy.ops.export_mesh, "stl"):
        with bpy.context.temp_override(
            active_object=accepted_object,
            object=accepted_object,
            selected_objects=[accepted_object],
            selected_editable_objects=[accepted_object],
        ):
            bpy.ops.export_mesh.stl(filepath=str(stl_path), use_selection=True, check_existing=False)
        return
    raise HY3DError("No STL export operator is available in this Blender build.")


def _validate_existing_stl(props) -> dict:
    if not getattr(props, "job_id", "").strip():
        raise HY3DError("Run Local TripoSR before validating STL.")
    accepted_model = _resolve_existing_file(getattr(props, "accepted_model_path", ""), suffix=".glb")
    if accepted_model is None:
        raise HY3DError("Accepted model path is not available.")
    accepted_dir = build_job_paths(workspace_root(), props.job_id, getattr(props, "version_id", "v1") or "v1").accepted_dir
    stl_path = accepted_dir / "accepted_model.stl"
    if not stl_path.exists() or not stl_path.is_file():
        raise HY3DError("accepted_model.stl is not available.")
    report = validate_stl_file(stl_path)
    write_json(accepted_dir / "stl_validation_report.json", report)
    write_json(accepted_dir / "printability_report.json", report.get("printability_report", {}))
    return report


def _path_openable(path: Path | None) -> bool:
    return path is not None and path.exists()


if BLENDER_AVAILABLE:  # pragma: no branch
    class HY3DLocalConnectorProperties(PropertyGroup):
        primary_image_path: StringProperty(name="Primary Image Path", default="")
        engine_job_id: StringProperty(name="Engine Job ID", default="")
        job_id: StringProperty(name="Job ID", default="")
        version_id: StringProperty(name="Version ID", default="v1")
        engine_output_dir: StringProperty(name="Engine Output Dir", default="")
        local_engine_status_path: StringProperty(name="Local Engine Status Path", default="")
        result_package_path: StringProperty(name="Result Package Path", default="")
        candidate_model_path: StringProperty(name="Candidate Model Path", default="")
        repaired_candidate_path: StringProperty(name="Repaired Candidate Path", default="")
        repaired_candidate_light_path: StringProperty(name="Light Repaired Candidate Path", default="")
        repaired_candidate_meshfix_path: StringProperty(name="MeshFix Candidate Path", default="")
        repaired_candidate_meshlab_path: StringProperty(name="MeshLab Candidate Path", default="")
        accepted_model_path: StringProperty(name="Accepted Model Path", default="")
        accepted_stl_path: StringProperty(name="Accepted STL Path", default="")
        stl_validation_report_path: StringProperty(name="STL Validation Report Path", default="")
        printability_report_path: StringProperty(name="Printability Report Path", default="")
        exports_dir: StringProperty(name="Exports Dir", default="")
        input_quality_status: StringProperty(name="Input Quality Status", default="")
        input_quality_warnings: StringProperty(name="Input Quality Warnings", default="")
        input_quality_report_path: StringProperty(name="Input Quality Report Path", default="")
        repair_profile: EnumProperty(
            name="Repair Profile",
            items=[
                ("safe_light", "Safe Light", ""),
                ("visual_preserve", "Visual Preserve", ""),
                ("printability", "Printability", ""),
                ("aggressive_close_holes", "Aggressive Close Holes", ""),
            ],
            default="safe_light",
        )
        current_status: StringProperty(name="Current Status", default=STATUS_NO_JOB)
        hy3d_imported: BoolProperty(name="HY3D Imported", default=False)
        self_check_status: StringProperty(name="Self Check Status", default="")
        last_status: StringProperty(name="Last Status", default="")
        last_error: StringProperty(name="Last Error", default="")
        timeout_seconds: IntProperty(name="Timeout Seconds", default=900, min=60, max=7200)


    class HY3D_LOCAL_CONNECTOR_OT_SelfCheck(Operator):
        bl_idname = "hy3d_local_connector.self_check"
        bl_label = "Self Check"

        def execute(self, context):
            props = context.scene.hy3d_local_connector
            payload = _local_engine_status()
            props.self_check_status = json.dumps(payload, indent=2)
            self.report({"INFO"}, f"Self Check ready: {ADDON_BUILD_ID}")
            return {"FINISHED"}


    class HY3D_LOCAL_CONNECTOR_OT_ResetSession(Operator):
        bl_idname = "hy3d_local_connector.reset_session"
        bl_label = "Reset Session"

        def execute(self, context):
            _reset_session(context.scene.hy3d_local_connector)
            self.report({"INFO"}, "Session reset.")
            return {"FINISHED"}


    class HY3D_LOCAL_CONNECTOR_OT_ClearHY3DObjects(Operator):
        bl_idname = "hy3d_local_connector.clear_hy3d_objects"
        bl_label = "Clear HY3D Objects From Scene"

        def execute(self, _context):
            removed = 0
            for obj in list(bpy.data.objects):
                if not _is_hy3d_scene_object(obj):
                    continue
                bpy.data.objects.remove(obj, do_unlink=True)
                removed += 1
            self.report({"INFO"}, f"Removed {removed} HY3D object(s).")
            return {"FINISHED"}


    class HY3D_LOCAL_CONNECTOR_OT_SelectPrimaryImage(Operator, ImportHelper):
        bl_idname = "hy3d_local_connector.select_primary_image"
        bl_label = "Select Primary Image"
        filename_ext = ""
        filter_glob: StringProperty(default="*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.avif", options={"HIDDEN"})

        def execute(self, context):
            props = context.scene.hy3d_local_connector
            path, error = _validate_primary_image(self.filepath)
            if path is None:
                self.report({"ERROR"}, error or "Invalid primary image.")
                return {"CANCELLED"}
            props.primary_image_path = str(path)
            self.report({"INFO"}, f"Selected {path.name}")
            return {"FINISHED"}


    class HY3D_LOCAL_CONNECTOR_OT_UseSmokeInput(Operator):
        bl_idname = "hy3d_local_connector.use_smoke_input"
        bl_label = "Use Smoke Input"

        def execute(self, context):
            props = context.scene.hy3d_local_connector
            smoke = _resolve_existing_file(SAMPLE_INPUT)
            if smoke is None:
                self.report({"ERROR"}, "Smoke input image is not available.")
                return {"CANCELLED"}
            props.primary_image_path = str(smoke)
            self.report({"INFO"}, "Smoke input selected.")
            return {"FINISHED"}


    class HY3D_LOCAL_CONNECTOR_OT_CheckLocalEngine(Operator):
        bl_idname = "hy3d_local_connector.check_local_engine"
        bl_label = "Check Local Engine"

        def execute(self, context):
            props = context.scene.hy3d_local_connector
            status = _local_engine_status()
            props.self_check_status = json.dumps(status, indent=2)
            if not all(
                [
                    status["wrapper_exists"],
                    status["venv_exists"],
                    status["python_exists"],
                    status["triposr_repo_exists"],
                    status["run_py_exists"],
                ]
            ):
                self.report({"ERROR"}, "Local TripoSR engine is not ready.")
                return {"CANCELLED"}
            self.report({"INFO"}, "Local TripoSR engine is ready.")
            return {"FINISHED"}


    class HY3D_LOCAL_CONNECTOR_OT_RunLocalTripoSR(Operator):
        bl_idname = "hy3d_local_connector.run_local_triposr"
        bl_label = "Run Local TripoSR"

        def execute(self, context):
            props = context.scene.hy3d_local_connector
            status = _local_engine_status()
            if not all(
                [
                    status["wrapper_exists"],
                    status["venv_exists"],
                    status["python_exists"],
                    status["triposr_repo_exists"],
                    status["run_py_exists"],
                ]
            ):
                self.report({"ERROR"}, "Local TripoSR engine is not ready.")
                return {"CANCELLED"}

            primary_image, error = _validate_primary_image(props.primary_image_path)
            if primary_image is None:
                self.report({"ERROR"}, error or "Primary image is invalid.")
                return {"CANCELLED"}
            quality_status, quality_warnings = _input_quality_summary(primary_image)
            props.input_quality_status = quality_status
            props.input_quality_warnings = quality_warnings
            if quality_status == "error":
                props.last_error = quality_warnings or "Input image quality check failed."
                self.report({"ERROR"}, props.last_error)
                return {"CANCELLED"}
            if quality_warnings:
                props.last_error = f"Input warning: {quality_warnings}"

            engine_job_id = _new_engine_job_id()
            props.version_id = "v1"
            output_dir = ENGINE_ROOT / "outputs" / engine_job_id
            output_dir.mkdir(parents=True, exist_ok=True)

            command = [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(WRAPPER_RUN),
                "-input_image",
                str(primary_image),
                "-output_dir",
                str(output_dir),
                "-job_id",
                engine_job_id,
                "-version_id",
                props.version_id or "v1",
            ]
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=int(props.timeout_seconds),
                    check=False,
                )
            except subprocess.TimeoutExpired:
                props.last_status = "failed"
                props.last_error = f"Local TripoSR timed out after {props.timeout_seconds} seconds."
                self.report({"ERROR"}, props.last_error)
                return {"CANCELLED"}
            except Exception as exc:
                props.last_status = "failed"
                props.last_error = str(exc)
                self.report({"ERROR"}, props.last_error)
                return {"CANCELLED"}

            run_report_path = output_dir / "run_report.json"
            if not run_report_path.exists():
                props.last_status = "failed"
                props.last_error = f"run_report.json was not created. Exit code: {completed.returncode}"
                self.report({"ERROR"}, props.last_error)
                return {"CANCELLED"}

            try:
                run_report = read_json(run_report_path)
            except Exception as exc:
                props.last_status = "failed"
                props.last_error = f"Failed to read run_report.json: {exc}"
                self.report({"ERROR"}, props.last_error)
                return {"CANCELLED"}

            props.last_status = str(run_report.get("status", "unknown"))
            if run_report.get("success") is True:
                result_package = _resolve_existing_file(run_report.get("result_package", ""), suffix=".zip")
                if result_package is None:
                    props.last_error = "run_report.json did not provide a valid result_package.zip."
                    self.report({"ERROR"}, props.last_error)
                    return {"CANCELLED"}
                _set_engine_generated_state(props, engine_job_id, output_dir, result_package)
                self.report({"INFO"}, "Result package generated. Next step: Import Local Result.")
                return {"FINISHED"}

            error_message = run_report.get("error") or completed.stderr or completed.stdout or "Local TripoSR failed."
            props.last_error = str(error_message)
            self.report({"ERROR"}, props.last_error)
            return {"CANCELLED"}


    class HY3D_LOCAL_CONNECTOR_OT_ImportLocalResult(Operator):
        bl_idname = "hy3d_local_connector.import_local_result"
        bl_label = "Import Local Result"

        def execute(self, context):
            props = context.scene.hy3d_local_connector
            package_path, error = _validate_result_package_path(props.result_package_path)
            if package_path is None:
                self.report({"ERROR"}, error or "Result package is invalid.")
                return {"CANCELLED"}
            try:
                _import_result_package_from_path(props, package_path)
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
            props.last_error = ""
            self.report({"INFO"}, f"Local result imported into HY3D: {_hy3d_job_dir_path(props)}")
            return {"FINISHED"}


    class HY3D_LOCAL_CONNECTOR_OT_ImportExistingResultPackage(Operator, ImportHelper):
        bl_idname = "hy3d_local_connector.import_existing_result_package"
        bl_label = "Import Existing Result Package"
        filename_ext = ".zip"
        filter_glob: StringProperty(default="*.zip", options={"HIDDEN"})

        def execute(self, context):
            props = context.scene.hy3d_local_connector
            package_path, error = _validate_result_package_path(self.filepath)
            if package_path is None:
                self.report({"ERROR"}, error or "Result package is invalid.")
                return {"CANCELLED"}
            props.result_package_path = str(package_path)
            props.engine_output_dir = str(package_path.parent)
            props.engine_job_id = package_path.parent.name
            try:
                _import_result_package_from_path(props, package_path)
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
            self.report({"INFO"}, f"Existing result package imported into HY3D: {_hy3d_job_dir_path(props)}")
            return {"FINISHED"}


    class HY3D_LOCAL_CONNECTOR_OT_ImportCandidateGLB(Operator):
        bl_idname = "hy3d_local_connector.import_candidate_glb"
        bl_label = "Import Original Candidate GLB"

        def execute(self, context):
            props = context.scene.hy3d_local_connector
            candidate = _resolve_existing_file(props.candidate_model_path, suffix=".glb")
            if candidate is None:
                self.report({"ERROR"}, "Candidate GLB path is not available.")
                return {"CANCELLED"}
            try:
                _import_candidate_glb_for_review(context, props, candidate, "original", "Candidate")
            except Exception as exc:
                self.report({"ERROR"}, f"Failed to import candidate GLB: {exc}")
                return {"CANCELLED"}
            self.report({"INFO"}, "Candidate GLB imported.")
            return {"FINISHED"}


    class HY3D_LOCAL_CONNECTOR_OT_ImportRepairedCandidateGLB(Operator):
        bl_idname = "hy3d_local_connector.import_repaired_candidate_glb"
        bl_label = "Import Light Repaired Candidate"

        def execute(self, context):
            props = context.scene.hy3d_local_connector
            repaired_candidate = _resolve_existing_file(props.repaired_candidate_light_path or props.repaired_candidate_path, suffix=".glb")
            if repaired_candidate is None:
                self.report({"ERROR"}, "Light repaired candidate GLB path is not available.")
                return {"CANCELLED"}
            try:
                _import_candidate_glb_for_review(context, props, repaired_candidate, "light", "Light repaired candidate")
            except Exception as exc:
                self.report({"ERROR"}, f"Failed to import light repaired candidate GLB: {exc}")
                return {"CANCELLED"}
            self.report({"INFO"}, "Light repaired candidate GLB imported.")
            return {"FINISHED"}


    class HY3D_LOCAL_CONNECTOR_OT_ImportMeshFixCandidateGLB(Operator):
        bl_idname = "hy3d_local_connector.import_meshfix_candidate_glb"
        bl_label = "Import MeshFix Candidate"

        def execute(self, context):
            props = context.scene.hy3d_local_connector
            repaired_candidate = _resolve_existing_file(props.repaired_candidate_meshfix_path, suffix=".glb")
            if repaired_candidate is None:
                self.report({"ERROR"}, "MeshFix candidate GLB path is not available.")
                return {"CANCELLED"}
            try:
                _import_candidate_glb_for_review(context, props, repaired_candidate, "meshfix", "MeshFix candidate")
            except Exception as exc:
                self.report({"ERROR"}, f"Failed to import MeshFix candidate GLB: {exc}")
                return {"CANCELLED"}
            self.report({"INFO"}, "MeshFix candidate GLB imported.")
            return {"FINISHED"}


    class HY3D_LOCAL_CONNECTOR_OT_ImportMeshLabCandidateGLB(Operator):
        bl_idname = "hy3d_local_connector.import_meshlab_candidate_glb"
        bl_label = "Import MeshLab Candidate"

        def execute(self, context):
            props = context.scene.hy3d_local_connector
            repaired_candidate = _resolve_existing_file(props.repaired_candidate_meshlab_path, suffix=".glb")
            if repaired_candidate is None:
                self.report({"ERROR"}, "MeshLab candidate GLB path is not available.")
                return {"CANCELLED"}
            try:
                _import_candidate_glb_for_review(context, props, repaired_candidate, "meshlab", "MeshLab candidate")
            except Exception as exc:
                self.report({"ERROR"}, f"Failed to import MeshLab candidate GLB: {exc}")
                return {"CANCELLED"}
            self.report({"INFO"}, "MeshLab candidate GLB imported.")
            return {"FINISHED"}


    class HY3D_LOCAL_CONNECTOR_OT_SaveBasicReview(Operator):
        bl_idname = "hy3d_local_connector.save_basic_review"
        bl_label = "Save Basic Review"

        def execute(self, context):
            props = context.scene.hy3d_local_connector
            if not props.job_id.strip():
                self.report({"ERROR"}, "Run Local TripoSR before saving a review.")
                return {"CANCELLED"}
            review = ReviewPayload(
                visual_score=3,
                geometry_score=3,
                object_similarity=3,
                holes_or_artifacts="not_reviewed",
                usable_as_base=True,
                repair_needed="unknown",
                notes="Basic manual review saved by HY3D Local Connector.",
            )
            try:
                review_path = save_manual_review(workspace_root(), props.job_id, props.version_id or "v1", review)
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
            self.report({"INFO"}, f"Saved {review_path.name}")
            return {"FINISHED"}


    class HY3D_LOCAL_CONNECTOR_OT_AcceptSelectedObject(Operator):
        bl_idname = "hy3d_local_connector.accept_selected_object"
        bl_label = "Accept Selected Object"

        def execute(self, context):
            props = context.scene.hy3d_local_connector
            candidate = _resolve_existing_file(props.candidate_model_path, suffix=".glb")
            if candidate is None:
                self.report({"ERROR"}, "Candidate GLB path is not available.")
                return {"CANCELLED"}
            obj = context.active_object
            if obj is None:
                self.report({"ERROR"}, "Select an object to export as accepted_model.glb.")
                return {"CANCELLED"}

            previous_selection = list(context.selected_objects)
            previous_active = context.view_layer.objects.active
            bpy.ops.object.select_all(action="DESELECT")
            obj.select_set(True)
            context.view_layer.objects.active = obj

            def exporter(destination: Path) -> None:
                destination.parent.mkdir(parents=True, exist_ok=True)
                bpy.ops.export_scene.gltf(filepath=str(destination), use_selection=True, export_format="GLB")

            try:
                accepted_path = promote_selected_object_to_accepted(
                    workspace_root(),
                    props.job_id,
                    props.version_id or "v1",
                    exporter=exporter,
                    accepted_object_name=obj.name,
                    source_candidate_path=str(candidate),
                    human_edited=True,
                )
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
            finally:
                bpy.ops.object.select_all(action="DESELECT")
                for previous in previous_selection:
                    previous.select_set(True)
                context.view_layer.objects.active = previous_active

            obj["hy3d_job_id"] = props.job_id
            obj["hy3d_role"] = "accepted"
            obj["hy3d_source_path"] = str(accepted_path)
            props.accepted_model_path = str(accepted_path)
            props.accepted_stl_path = ""
            props.stl_validation_report_path = ""
            props.printability_report_path = ""
            props.exports_dir = ""
            _set_status(props, STATUS_ACCEPTED)
            self.report({"INFO"}, "Accepted GLB exported.")
            return {"FINISHED"}


    class HY3D_LOCAL_CONNECTOR_OT_ExportSTLFromAccepted(Operator):
        bl_idname = "hy3d_local_connector.export_stl_from_accepted"
        bl_label = "Export STL From Accepted"

        def execute(self, context):
            props = context.scene.hy3d_local_connector
            accepted_model = _resolve_existing_file(props.accepted_model_path, suffix=".glb")
            if accepted_model is None:
                self.report({"ERROR"}, "Accepted model path is not available.")
                return {"CANCELLED"}

            def exporter(_accepted_glb: Path, stl_path: Path) -> None:
                accepted_object = _find_imported_object(props.job_id, "accepted")
                imported_temporarily = None
                if accepted_object is None:
                    existing_names = {obj.name for obj in bpy.data.objects}
                    try:
                        bpy.ops.import_scene.gltf(filepath=str(_accepted_glb))
                    except RuntimeError as exc:
                        raise HY3DError(f"Failed to import accepted GLB for STL export: {exc}") from exc
                    imported = [obj for obj in context.selected_objects if obj.name not in existing_names] or list(context.selected_objects)
                    if imported:
                        accepted_object = imported[0]
                        imported_temporarily = imported
                        accepted_object["hy3d_job_id"] = props.job_id
                        accepted_object["hy3d_role"] = "accepted"
                if accepted_object is None:
                    raise HY3DError("No accepted object is available for STL export.")
                previous_selection = list(context.selected_objects)
                previous_active = context.view_layer.objects.active
                bpy.ops.object.select_all(action="DESELECT")
                accepted_object.select_set(True)
                context.view_layer.objects.active = accepted_object
                _export_selected_object_to_stl(stl_path, accepted_object)
                bpy.ops.object.select_all(action="DESELECT")
                for previous in previous_selection:
                    previous.select_set(True)
                context.view_layer.objects.active = previous_active
                if imported_temporarily:
                    for imported_object in imported_temporarily:
                        bpy.data.objects.remove(imported_object, do_unlink=True)

            try:
                stl_path = export_stl_from_accepted(workspace_root(), props.job_id, exporter=exporter)
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
            props.accepted_stl_path = str(stl_path)
            export_dir = _sync_exports_from_accepted(props)
            _set_status(props, STATUS_STL_EXPORTED)
            props.last_status = STATUS_STL_EXPORTED
            props.last_error = ""
            self.report({"INFO"}, f"Exported {stl_path.name} to {export_dir}")
            return {"FINISHED"}


    class HY3D_LOCAL_CONNECTOR_OT_ValidateSTL(Operator):
        bl_idname = "hy3d_local_connector.validate_stl"
        bl_label = "Validate STL"

        def execute(self, context):
            props = context.scene.hy3d_local_connector
            try:
                report = _validate_existing_stl(props)
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
            accepted_dir = _accepted_dir_path(props)
            if accepted_dir is not None:
                props.stl_validation_report_path = str(accepted_dir / "stl_validation_report.json")
                props.printability_report_path = str(accepted_dir / "printability_report.json")
            _sync_exports_from_accepted(props)
            props.last_status = STATUS_STL_VALIDATED
            props.last_error = ""
            _set_status(props, STATUS_STL_VALIDATED)
            self.report({"INFO"}, f"STL validation: {report.get('printability_status', 'unknown')}")
            return {"FINISHED"}


    class HY3D_LOCAL_CONNECTOR_OT_OpenEngineOutputFolder(Operator):
        bl_idname = "hy3d_local_connector.open_engine_output_folder"
        bl_label = "Open Engine Output Folder"

        def execute(self, _context):
            target = _engine_output_dir_path(_context.scene.hy3d_local_connector)
            if not _path_openable(target):
                self.report({"ERROR"}, "Engine output folder is not available.")
                return {"CANCELLED"}
            bpy.ops.wm.path_open(filepath=str(target))
            return {"FINISHED"}


    class HY3D_LOCAL_CONNECTOR_OT_OpenHY3DJobFolder(Operator):
        bl_idname = "hy3d_local_connector.open_hy3d_job_folder"
        bl_label = "Open HY3D Job Folder"

        def execute(self, context):
            target = _hy3d_job_dir_path(context.scene.hy3d_local_connector)
            if not _path_openable(target):
                self.report({"ERROR"}, "HY3D job folder is not available.")
                return {"CANCELLED"}
            bpy.ops.wm.path_open(filepath=str(target))
            return {"FINISHED"}


    class HY3D_LOCAL_CONNECTOR_OT_OpenAcceptedFolder(Operator):
        bl_idname = "hy3d_local_connector.open_accepted_folder"
        bl_label = "Open Accepted Folder"

        def execute(self, context):
            target = _accepted_dir_path(context.scene.hy3d_local_connector)
            if not _path_openable(target):
                self.report({"ERROR"}, "Accepted folder is not available.")
                return {"CANCELLED"}
            bpy.ops.wm.path_open(filepath=str(target))
            return {"FINISHED"}


    class HY3D_LOCAL_CONNECTOR_OT_OpenValidationFolder(Operator):
        bl_idname = "hy3d_local_connector.open_validation_folder"
        bl_label = "Open Validation Folder"

        def execute(self, context):
            target = _validation_dir_path(context.scene.hy3d_local_connector)
            if not _path_openable(target):
                self.report({"ERROR"}, "Validation folder is not available.")
                return {"CANCELLED"}
            bpy.ops.wm.path_open(filepath=str(target))
            return {"FINISHED"}


    class HY3D_LOCAL_CONNECTOR_OT_OpenExportsFolder(Operator):
        bl_idname = "hy3d_local_connector.open_exports_folder"
        bl_label = "Open Exports Folder"

        def execute(self, context):
            target = _exports_dir_path(context.scene.hy3d_local_connector)
            if not _path_openable(target):
                self.report({"ERROR"}, "Exports folder is not available.")
                return {"CANCELLED"}
            bpy.ops.wm.path_open(filepath=str(target))
            return {"FINISHED"}


    class HY3D_LOCAL_CONNECTOR_OT_OpenWorkspaceFolder(Operator):
        bl_idname = "hy3d_local_connector.open_workspace_folder"
        bl_label = "Open Workspace Folder"

        def execute(self, _context):
            workspace = _resolve_existing_dir(workspace_root())
            if workspace is None:
                self.report({"ERROR"}, "Workspace folder is not available.")
                return {"CANCELLED"}
            bpy.ops.wm.path_open(filepath=str(workspace))
            return {"FINISHED"}


    class HY3D_LOCAL_CONNECTOR_PT_MainPanel(Panel):
        bl_idname = "HY3D_LOCAL_CONNECTOR_PT_main_panel"
        bl_label = "HY3D Local Connector"
        bl_space_type = "VIEW_3D"
        bl_region_type = "UI"
        bl_category = "HY3D Local"

        def draw(self, context):
            props = context.scene.hy3d_local_connector
            layout = self.layout

            box = layout.box()
            box.label(text="Self Check")
            box.label(text=f"Build ID: {ADDON_BUILD_ID}")
            box.operator("hy3d_local_connector.self_check")
            box.operator("hy3d_local_connector.reset_session")
            box.operator("hy3d_local_connector.clear_hy3d_objects")

            box = layout.box()
            box.label(text="Input")
            box.prop(props, "primary_image_path", text="Primary Image")
            if props.input_quality_status:
                box.label(text=f"Input Quality: {props.input_quality_status}")
            if props.input_quality_warnings:
                box.label(text=f"Input Warnings: {props.input_quality_warnings}")
            row = box.row(align=True)
            row.operator("hy3d_local_connector.select_primary_image")
            row.operator("hy3d_local_connector.use_smoke_input")

            box = layout.box()
            box.label(text="Local TripoSR")
            box.prop(props, "timeout_seconds")
            box.operator("hy3d_local_connector.check_local_engine")
            box.operator("hy3d_local_connector.run_local_triposr")
            row = box.row()
            row.enabled = _validate_result_package_path(props.result_package_path)[0] is not None
            row.operator("hy3d_local_connector.import_local_result")
            box.operator("hy3d_local_connector.import_existing_result_package")

            box = layout.box()
            box.label(text="Candidate")
            box.prop(props, "repair_profile")
            row = box.row()
            row.enabled = _has_valid_candidate_model_path(props)
            row.operator("hy3d_local_connector.import_candidate_glb")
            row = box.row()
            row.enabled = _has_valid_light_candidate_path(props) or _has_valid_repaired_candidate_path(props)
            row.operator("hy3d_local_connector.import_repaired_candidate_glb")
            row = box.row()
            row.enabled = _has_valid_meshfix_candidate_path(props)
            row.operator("hy3d_local_connector.import_meshfix_candidate_glb")
            row = box.row()
            row.enabled = _has_valid_meshlab_candidate_path(props)
            row.operator("hy3d_local_connector.import_meshlab_candidate_glb")

            box = layout.box()
            box.label(text="Review")
            row = box.row()
            row.enabled = bool(props.job_id.strip())
            row.operator("hy3d_local_connector.save_basic_review")
            row = box.row()
            row.enabled = _has_valid_candidate_model_path(props)
            row.operator("hy3d_local_connector.accept_selected_object")

            box = layout.box()
            box.label(text="STL")
            row = box.row()
            row.enabled = _stl_export_ready(props)
            row.operator("hy3d_local_connector.export_stl_from_accepted")
            row = box.row()
            row.enabled = _validate_stl_ready(props)
            row.operator("hy3d_local_connector.validate_stl")

            box = layout.box()
            box.label(text="Workspace")
            box.label(text=f"Current Status: {props.current_status or STATUS_NO_JOB}")
            box.label(text=f"Engine Job: {props.engine_job_id or '(none)'}")
            box.label(text=f"HY3D Job: {props.job_id or '(none)'}")
            box.label(text=f"Version: {props.version_id or 'v1'}")
            box.label(text=f"Engine Output Folder: {props.engine_output_dir or '(none)'}")
            box.label(text=f"Result ZIP: {props.result_package_path or '(none)'}")
            box.label(text=f"HY3D Job Folder: {str(_hy3d_job_dir_path(props)) if _hy3d_job_dir_path(props) else '(none)'}")
            box.label(text=f"Candidate: {props.candidate_model_path or '(none)'}")
            box.label(text=f"Light Candidate: {props.repaired_candidate_light_path or props.repaired_candidate_path or '(none)'}")
            box.label(text=f"MeshFix Candidate: {props.repaired_candidate_meshfix_path or '(none)'}")
            box.label(text=f"MeshLab Candidate: {props.repaired_candidate_meshlab_path or '(none)'}")
            box.label(text=f"Accepted: {props.accepted_model_path or '(none)'}")
            box.label(text=f"STL Path: {props.accepted_stl_path or '(none)'}")
            box.label(text=f"Exports Folder: {props.exports_dir or '(none)'}")
            box.label(text=f"Input Quality Report: {props.input_quality_report_path or '(none)'}")
            box.operator("hy3d_local_connector.open_workspace_folder")
            row = box.row(align=True)
            row.enabled = _path_openable(_engine_output_dir_path(props))
            row.operator("hy3d_local_connector.open_engine_output_folder")
            row = box.row(align=True)
            row.enabled = _path_openable(_hy3d_job_dir_path(props))
            row.operator("hy3d_local_connector.open_hy3d_job_folder")
            row = box.row(align=True)
            row.enabled = _path_openable(_accepted_dir_path(props))
            row.operator("hy3d_local_connector.open_accepted_folder")
            row = box.row(align=True)
            row.enabled = _path_openable(_validation_dir_path(props))
            row.operator("hy3d_local_connector.open_validation_folder")
            row = box.row(align=True)
            row.enabled = _path_openable(_exports_dir_path(props))
            row.operator("hy3d_local_connector.open_exports_folder")
            if props.last_status:
                box.label(text=f"Last Status: {props.last_status}")
            if props.last_error:
                box.label(text=f"Last Error: {props.last_error}")


    CLASSES = (
        HY3DLocalConnectorProperties,
        HY3D_LOCAL_CONNECTOR_OT_SelfCheck,
        HY3D_LOCAL_CONNECTOR_OT_ResetSession,
        HY3D_LOCAL_CONNECTOR_OT_ClearHY3DObjects,
        HY3D_LOCAL_CONNECTOR_OT_SelectPrimaryImage,
        HY3D_LOCAL_CONNECTOR_OT_UseSmokeInput,
        HY3D_LOCAL_CONNECTOR_OT_CheckLocalEngine,
        HY3D_LOCAL_CONNECTOR_OT_RunLocalTripoSR,
        HY3D_LOCAL_CONNECTOR_OT_ImportLocalResult,
        HY3D_LOCAL_CONNECTOR_OT_ImportExistingResultPackage,
        HY3D_LOCAL_CONNECTOR_OT_ImportCandidateGLB,
        HY3D_LOCAL_CONNECTOR_OT_ImportRepairedCandidateGLB,
        HY3D_LOCAL_CONNECTOR_OT_ImportMeshFixCandidateGLB,
        HY3D_LOCAL_CONNECTOR_OT_ImportMeshLabCandidateGLB,
        HY3D_LOCAL_CONNECTOR_OT_SaveBasicReview,
        HY3D_LOCAL_CONNECTOR_OT_AcceptSelectedObject,
        HY3D_LOCAL_CONNECTOR_OT_ExportSTLFromAccepted,
        HY3D_LOCAL_CONNECTOR_OT_ValidateSTL,
        HY3D_LOCAL_CONNECTOR_OT_OpenEngineOutputFolder,
        HY3D_LOCAL_CONNECTOR_OT_OpenHY3DJobFolder,
        HY3D_LOCAL_CONNECTOR_OT_OpenAcceptedFolder,
        HY3D_LOCAL_CONNECTOR_OT_OpenValidationFolder,
        HY3D_LOCAL_CONNECTOR_OT_OpenExportsFolder,
        HY3D_LOCAL_CONNECTOR_OT_OpenWorkspaceFolder,
        HY3D_LOCAL_CONNECTOR_PT_MainPanel,
    )


    def register():
        for cls in CLASSES:
            bpy.utils.register_class(cls)
        bpy.types.Scene.hy3d_local_connector = PointerProperty(type=HY3DLocalConnectorProperties)


    def unregister():
        if hasattr(bpy.types.Scene, "hy3d_local_connector"):
            del bpy.types.Scene.hy3d_local_connector
        for cls in reversed(CLASSES):
            bpy.utils.unregister_class(cls)


else:
    CLASSES = ()

    def register():
        return None


    def unregister():
        return None


__all__ = [
    "ADDON_BUILD_ID",
    "BLENDER_AVAILABLE",
    "CORE_ROOT",
    "ENGINE_REPO",
    "ENGINE_ROOT",
    "ENGINE_VENV",
    "EXPORTS_ROOT",
    "LOCAL_CONNECTOR_ROOT",
    "PROJECT_ROOT",
    "SAMPLE_INPUT",
    "STATUS_ACCEPTED",
    "STATUS_CANDIDATE_IMPORTED",
    "STATUS_ENGINE_GENERATED",
    "STATUS_IMPORTED_TO_HY3D",
    "STATUS_NO_JOB",
    "STATUS_STL_EXPORTED",
    "STATUS_STL_VALIDATED",
    "VALID_IMAGE_SUFFIXES",
    "WRAPPER_RUN",
    "_accepted_dir_path",
    "_engine_output_dir_path",
    "_exports_dir_path",
    "_exports_job_dir",
    "_has_valid_accepted_model_path",
    "_has_valid_light_candidate_path",
    "_has_valid_meshfix_candidate_path",
    "_has_valid_meshlab_candidate_path",
    "_has_valid_repaired_candidate_path",
    "_import_result_package_into_session",
    "_import_result_package_from_path",
    "_is_hy3d_scene_object",
    "_hy3d_job_dir_path",
    "_local_engine_status",
    "_local_engine_status_file_path",
    "_path_openable",
    "_reset_session",
    "_resolve_existing_dir",
    "_resolve_existing_file",
    "_validation_dir_path",
    "_set_engine_generated_state",
    "_set_imported_to_hy3d_state",
    "_status_payload",
    "_sync_exports_from_accepted",
    "_stl_export_ready",
    "_validate_existing_stl",
    "_validate_stl_ready",
    "_validate_primary_image",
    "_validate_result_package_path",
    "bl_info",
    "register",
    "unregister",
    "workspace_root",
]
