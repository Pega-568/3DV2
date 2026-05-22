from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(r"E:\3DV4\hy3d_v2")
CORE_ROOT = PROJECT_ROOT / "hy3d_core"
LOCAL_CONNECTOR_ROOT = Path(r"E:\3DV4\hy3d_local_connector_addon\hy3d_local_connector")
WRAPPER_RUN = Path(r"E:\3D_ENGINES\wrappers\run_triposr_local.ps1")
ENGINE_ROOT = Path(r"E:\3D_ENGINES\triposr-local")
ENGINE_VENV = ENGINE_ROOT / ".venv"
ENGINE_REPO = ENGINE_ROOT / "TripoSR"
SAMPLE_INPUT = PROJECT_ROOT / "test_assets" / "real_smoke_input.png"
VALID_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".avif"}
ADDON_BUILD_ID = f"hy3d_local_connector_{datetime.now().strftime('%Y%m%d_%H%M')}"

PROJECT_PARENT = PROJECT_ROOT.parent
if str(PROJECT_PARENT) not in sys.path:
    sys.path.insert(0, str(PROJECT_PARENT))

from hy3d_v2.hy3d_core.job_service import (  # noqa: E402
    HY3DError,
    create_job,
    export_stl_from_accepted,
    import_result_package,
    promote_selected_object_to_accepted,
    save_manual_review,
)
from hy3d_v2.hy3d_core.models import ReviewPayload  # noqa: E402
from hy3d_v2.hy3d_core.utils.files import read_json, utc_now_iso  # noqa: E402

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
    from bpy.props import IntProperty, PointerProperty, StringProperty
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


def _has_valid_candidate_model_path(props) -> bool:
    return _resolve_existing_file(getattr(props, "candidate_model_path", ""), suffix=".glb") is not None


def _has_valid_accepted_model_path(props) -> bool:
    return _resolve_existing_file(getattr(props, "accepted_model_path", ""), suffix=".glb") is not None


def _stl_export_ready(props) -> bool:
    return bool(getattr(props, "job_id", "").strip()) and _has_valid_accepted_model_path(props)


def _local_engine_status() -> dict[str, object]:
    python_exe = ENGINE_VENV / "Scripts" / "python.exe"
    run_py = ENGINE_REPO / "run.py"
    return {
        "build_id": ADDON_BUILD_ID,
        "addon_path": str(LOCAL_CONNECTOR_ROOT),
        "workspace": str(workspace_root()),
        "wrapper_exists": WRAPPER_RUN.exists(),
        "venv_exists": ENGINE_VENV.exists(),
        "python_exists": python_exe.exists(),
        "triposr_repo_exists": ENGINE_REPO.exists(),
        "run_py_exists": run_py.exists(),
        "sample_input_exists": SAMPLE_INPUT.exists(),
    }


def _reset_session(props) -> None:
    props.primary_image_path = ""
    props.job_id = ""
    props.version_id = "v1"
    props.engine_output_dir = ""
    props.result_package_path = ""
    props.candidate_model_path = ""
    props.accepted_model_path = ""
    props.self_check_status = ""
    props.last_status = ""
    props.last_error = ""


def _find_imported_object(job_id: str, role: str):
    if not BLENDER_AVAILABLE:
        return None
    for obj in bpy.data.objects:
        if obj.get("hy3d_job_id") == job_id and obj.get("hy3d_role") == role:
            return obj
    return None


def _import_result_package_into_session(props, package_path: Path) -> dict:
    manifest = import_result_package(workspace_root(), props.job_id, package_path, version_id=props.version_id or "v1")
    props.result_package_path = str(package_path)
    props.candidate_model_path = manifest["candidate_path"]
    props.accepted_model_path = ""
    return manifest


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


if BLENDER_AVAILABLE:  # pragma: no branch
    class HY3DLocalConnectorProperties(PropertyGroup):
        primary_image_path: StringProperty(name="Primary Image Path", default="")
        job_id: StringProperty(name="Job ID", default="")
        version_id: StringProperty(name="Version ID", default="v1")
        engine_output_dir: StringProperty(name="Engine Output Dir", default="")
        result_package_path: StringProperty(name="Result Package Path", default="")
        candidate_model_path: StringProperty(name="Candidate Model Path", default="")
        accepted_model_path: StringProperty(name="Accepted Model Path", default="")
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

            try:
                manifest = create_job(workspace_root(), primary_image)
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}

            props.job_id = manifest["job_id"]
            props.version_id = "v1"
            props.candidate_model_path = ""
            props.accepted_model_path = ""
            props.result_package_path = ""
            props.last_error = ""
            output_dir = ENGINE_ROOT / "outputs" / props.job_id
            output_dir.mkdir(parents=True, exist_ok=True)
            props.engine_output_dir = str(output_dir)

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
                props.job_id,
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
                props.result_package_path = str(result_package)
                self.report({"INFO"}, "Local TripoSR run completed.")
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
            if not props.job_id.strip():
                self.report({"ERROR"}, "Run Local TripoSR before importing a result.")
                return {"CANCELLED"}
            package_path, error = _validate_result_package_path(props.result_package_path)
            if package_path is None:
                self.report({"ERROR"}, error or "Result package is invalid.")
                return {"CANCELLED"}
            try:
                _import_result_package_into_session(props, package_path)
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
            self.report({"INFO"}, "Local result imported into workspace.")
            return {"FINISHED"}


    class HY3D_LOCAL_CONNECTOR_OT_ImportCandidateGLB(Operator):
        bl_idname = "hy3d_local_connector.import_candidate_glb"
        bl_label = "Import Candidate GLB"

        def execute(self, context):
            props = context.scene.hy3d_local_connector
            candidate = _resolve_existing_file(props.candidate_model_path, suffix=".glb")
            if candidate is None:
                self.report({"ERROR"}, "Candidate GLB path is not available.")
                return {"CANCELLED"}
            existing_names = {obj.name for obj in bpy.data.objects}
            try:
                bpy.ops.import_scene.gltf(filepath=str(candidate))
            except Exception as exc:
                self.report({"ERROR"}, f"Failed to import candidate GLB: {exc}")
                return {"CANCELLED"}
            imported = [obj for obj in context.selected_objects if obj.name not in existing_names] or list(context.selected_objects)
            for obj in imported:
                obj["hy3d_role"] = "candidate"
                obj["hy3d_source_path"] = str(candidate)
                obj["hy3d_job_id"] = props.job_id
            self.report({"INFO"}, "Candidate GLB imported.")
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
            self.report({"INFO"}, f"Exported {stl_path.name}")
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

            box = layout.box()
            box.label(text="Input")
            box.prop(props, "primary_image_path", text="Primary Image")
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

            box = layout.box()
            box.label(text="Candidate")
            row = box.row()
            row.enabled = _has_valid_candidate_model_path(props)
            row.operator("hy3d_local_connector.import_candidate_glb")

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

            box = layout.box()
            box.label(text="Workspace")
            box.operator("hy3d_local_connector.open_workspace_folder")
            box.label(text=f"Job: {props.job_id or '(none)'}")
            box.label(text=f"Version: {props.version_id or 'v1'}")
            box.label(text=f"Result ZIP: {props.result_package_path or '(none)'}")
            box.label(text=f"Candidate: {props.candidate_model_path or '(none)'}")
            box.label(text=f"Accepted: {props.accepted_model_path or '(none)'}")
            if props.last_status:
                box.label(text=f"Last Status: {props.last_status}")
            if props.last_error:
                box.label(text=f"Last Error: {props.last_error}")


    CLASSES = (
        HY3DLocalConnectorProperties,
        HY3D_LOCAL_CONNECTOR_OT_SelfCheck,
        HY3D_LOCAL_CONNECTOR_OT_ResetSession,
        HY3D_LOCAL_CONNECTOR_OT_SelectPrimaryImage,
        HY3D_LOCAL_CONNECTOR_OT_UseSmokeInput,
        HY3D_LOCAL_CONNECTOR_OT_CheckLocalEngine,
        HY3D_LOCAL_CONNECTOR_OT_RunLocalTripoSR,
        HY3D_LOCAL_CONNECTOR_OT_ImportLocalResult,
        HY3D_LOCAL_CONNECTOR_OT_ImportCandidateGLB,
        HY3D_LOCAL_CONNECTOR_OT_SaveBasicReview,
        HY3D_LOCAL_CONNECTOR_OT_AcceptSelectedObject,
        HY3D_LOCAL_CONNECTOR_OT_ExportSTLFromAccepted,
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
    "LOCAL_CONNECTOR_ROOT",
    "PROJECT_ROOT",
    "SAMPLE_INPUT",
    "VALID_IMAGE_SUFFIXES",
    "WRAPPER_RUN",
    "_has_valid_accepted_model_path",
    "_import_result_package_into_session",
    "_local_engine_status",
    "_reset_session",
    "_resolve_existing_dir",
    "_resolve_existing_file",
    "_stl_export_ready",
    "_validate_primary_image",
    "_validate_result_package_path",
    "bl_info",
    "register",
    "unregister",
    "workspace_root",
]
