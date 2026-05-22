from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))

from hy3d_v2.hy3d_core.job_service import (  # noqa: E402
    HY3DError,
    build_job_paths,
    create_job,
    create_job_package,
    export_stl_from_accepted,
    import_result_package,
    promote_edited_model_to_accepted,
    promote_selected_object_to_accepted,
    save_edited_model,
    save_manual_review,
)
from hy3d_v2.hy3d_core.models import ReferenceView, ReviewPayload  # noqa: E402
from hy3d_v2.hy3d_core.utils.files import copy_file, read_json, utc_now_iso, write_json  # noqa: E402

bl_info = {
    "name": "HY3D v2",
    "author": "OpenAI Codex",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > HY3D v2",
    "description": "GLB-first local review workflow for external 3D generation",
    "category": "3D View",
}

try:  # pragma: no cover - Blender-only import
    import bpy
    from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty
    from bpy.types import Operator, Panel, PropertyGroup

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

    def StringProperty(**_kwargs):  # type: ignore[misc]
        return None

    def BoolProperty(**_kwargs):  # type: ignore[misc]
        return None

    def EnumProperty(**_kwargs):  # type: ignore[misc]
        return None

    def IntProperty(**_kwargs):  # type: ignore[misc]
        return None


CLOUD_ROOT_WINDOWS_DEFAULT = r"G:\Mi unidad\HY3D_V2_CLOUD"
CLOUD_ROOT_COLAB_DEFAULT = "/content/drive/MyDrive/HY3D_V2_CLOUD"
CLOUD_SUBDIRS = ("incoming", "processing", "completed", "failed", "logs", "notebooks")
ADDON_BUILD_ID = "hy3d_v2_20260520_1155_routesafe"
SOURCE_PROJECT_ROOT_WINDOWS = Path(r"E:\3DV4\hy3d_v2")


def addon_root() -> Path:
    return PROJECT_ROOT


def workspace_root() -> Path:
    if BLENDER_AVAILABLE:
        base = Path(bpy.utils.user_resource("DATAFILES", path="hy3d_v2_workspace", create=True))
        base.mkdir(parents=True, exist_ok=True)
        return base
    fallback = PROJECT_ROOT / "_workspace"
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


def _resolve_existing_file(value, suffix=None):
    raw = _normalize_path_string(value)
    if not raw or not str(raw).strip():
        return None
    path = Path(raw)
    if str(path) in ("", "."):
        return None
    if not path.exists() or not path.is_file():
        return None
    if suffix and path.suffix.lower() != suffix.lower():
        return None
    return path


def _resolve_existing_dir(value):
    raw = _normalize_path_string(value)
    if not raw or not str(raw).strip():
        return None
    path = Path(raw)
    if str(path) in ("", "."):
        return None
    if not path.exists() or not path.is_dir():
        return None
    return path


def _has_valid_candidate_path(props) -> bool:
    return _resolve_existing_file(getattr(props, "candidate_path", ""), suffix=".glb") is not None


def _has_valid_accepted_model_path(props) -> bool:
    return _resolve_existing_file(getattr(props, "accepted_model_path", ""), suffix=".glb") is not None


def _has_valid_result_package_path(props) -> bool:
    return _resolve_existing_file(getattr(props, "result_package_path", ""), suffix=".zip") is not None


def _has_valid_job_package_path(props) -> bool:
    return _resolve_existing_file(getattr(props, "job_package_path", ""), suffix=".zip") is not None


def _has_valid_cloud_result_package_path(props) -> bool:
    return _resolve_existing_file(getattr(props, "cloud_result_package_path", ""), suffix=".zip") is not None


def _has_valid_cloud_root(props) -> bool:
    return _resolve_existing_dir(getattr(props, "cloud_root_folder", "")) is not None


def _ui_disables_candidate_import_without_candidate(props) -> bool:
    return not _has_valid_candidate_path(props)


def _has_imported_candidate_object(props) -> bool:
    if not BLENDER_AVAILABLE:
        return False
    for obj in bpy.data.objects:
        if obj.get("hy3d_job_id") == props.job_id and obj.get("hy3d_version_id") == props.version_id and obj.get("hy3d_role") == "candidate":
            return True
    return False


def _accepted_stl_path(props) -> Path | None:
    accepted_model = _resolve_existing_file(getattr(props, "accepted_model_path", ""), suffix=".glb")
    if accepted_model is None:
        return None
    stl_path = accepted_model.parent / "accepted_model.stl"
    return stl_path if stl_path.exists() and stl_path.is_file() else None


def _edited_model_path(props) -> Path | None:
    job_dir = _resolve_existing_dir(workspace_root() / "jobs" / props.job_id)
    if job_dir is None:
        return None
    edited_path = job_dir / "versions" / props.version_id / "edited" / "edited_model.glb"
    return edited_path if edited_path.exists() and edited_path.is_file() else None


def _ui_state(props) -> str:
    job_dir = _resolve_existing_dir(workspace_root() / "jobs" / props.job_id)
    if job_dir is None:
        return "no_job"
    if _accepted_stl_path(props) is not None:
        return "stl_exported"
    if _has_valid_accepted_model_path(props):
        return "accepted_created"
    if _has_imported_candidate_object(props):
        return "candidate_imported"
    if _has_valid_candidate_path(props):
        return "result_imported"
    return "job_created"


def _selected_reference_views(props) -> list[ReferenceView]:
    views: list[ReferenceView] = []
    reference_view = None
    for suffix in (".png", ".jpg", ".jpeg", ".webp", ".avif", ".bmp"):
        reference_view = _resolve_existing_file(getattr(props, "additional_view_path", ""), suffix=suffix)
        if reference_view is not None:
            break
    if reference_view is not None:
        views.append(ReferenceView(path=reference_view, view_type=props.additional_view_type))
    return views


def _sample_input_path() -> Path:
    preferred = SOURCE_PROJECT_ROOT_WINDOWS / "test_assets" / "sample_input.png"
    if preferred.exists():
        return preferred
    return PROJECT_ROOT / "test_assets" / "sample_input.png"


def _validate_primary_image_for_job_creation(value) -> tuple[Path | None, str | None]:
    raw = _normalize_path_string(value)
    if not raw:
        return None, "Please select a primary image before creating a job."
    if raw == ".":
        return None, "Invalid primary image path."
    path = Path(raw)
    if not path.exists():
        return None, "Primary image file does not exist."
    if not path.is_file():
        return None, "Primary image path is not a file."
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".avif", ".bmp"}:
        return None, "Unsupported image format."
    return path, None


def _active_job_dir(props) -> Path:
    return workspace_root() / "jobs" / props.job_id


def _cloud_names(job_id: str) -> dict[str, str]:
    return {
        "job_package": f"{job_id}_job_package.zip",
        "result_package": f"{job_id}_result_package.zip",
        "status_json": f"{job_id}_status.json",
        "error_json": f"{job_id}_error.json",
        "engine_log": f"{job_id}_engine_log.txt",
    }


def _cloud_status_path(root: Path, job_id: str) -> Path:
    return build_job_paths(root, job_id).job_dir / "cloud_status.json"


def _job_package_path(root: Path, job_id: str, version_id: str = "v1") -> Path:
    return build_job_paths(root, job_id, version_id).job_dir / "job_package.zip"


def _ensure_cloud_directories(cloud_root_value) -> dict[str, Path]:
    cloud_root = _resolve_existing_dir(cloud_root_value)
    if cloud_root is None:
        raise HY3DError("Cloud root folder is not configured or does not exist.")
    directories = {"root": cloud_root}
    for name in CLOUD_SUBDIRS:
        path = cloud_root / name
        path.mkdir(parents=True, exist_ok=True)
        directories[name] = path
    return directories


def _read_local_cloud_status(root: Path, job_id: str) -> dict:
    status_path = _cloud_status_path(root, job_id)
    if status_path.exists() and status_path.is_file():
        try:
            return read_json(status_path)
        except Exception:
            return {}
    return {}


def send_job_to_cloud(root: Path, job_id: str, cloud_root_value, version_id: str = "v1") -> dict:
    if not job_id:
        raise HY3DError("No active job available. Create a job package first.")
    job_dir = _resolve_existing_dir(build_job_paths(root, job_id, version_id).job_dir)
    if job_dir is None:
        raise HY3DError("No active job folder available. Create a job package first.")
    job_package = _resolve_existing_file(_job_package_path(root, job_id, version_id), suffix=".zip")
    if job_package is None:
        raise HY3DError("job_package.zip is missing for the active job.")
    directories = _ensure_cloud_directories(cloud_root_value)
    names = _cloud_names(job_id)
    incoming_package = copy_file(job_package, directories["incoming"] / names["job_package"])
    payload = {
        "job_id": job_id,
        "cloud_root": str(directories["root"]),
        "incoming_package": str(incoming_package),
        "status": "sent_to_cloud",
        "sent_at": utc_now_iso(),
        "expected_result_package": names["result_package"],
        "expected_status_json": names["status_json"],
    }
    write_json(_cloud_status_path(root, job_id), payload)
    return payload


def check_cloud_results(root: Path, job_id: str, cloud_root_value) -> dict:
    if not job_id:
        raise HY3DError("No active job available. Create a job package first.")
    directories = _ensure_cloud_directories(cloud_root_value)
    names = _cloud_names(job_id)
    completed_result = directories["completed"] / names["result_package"]
    completed_status = directories["completed"] / names["status_json"]
    processing_package = directories["processing"] / names["job_package"]
    processing_status = directories["processing"] / names["status_json"]
    incoming_package = directories["incoming"] / names["job_package"]
    failed_error = directories["failed"] / names["error_json"]
    failed_log = directories["failed"] / names["engine_log"]
    payload = _read_local_cloud_status(root, job_id)
    payload.update(
        {
            "job_id": job_id,
            "cloud_root": str(directories["root"]),
            "checked_at": utc_now_iso(),
            "expected_result_package": names["result_package"],
            "expected_status_json": names["status_json"],
            "result_package_path": "",
            "failed_error_path": "",
            "failed_log_path": "",
        }
    )
    if completed_result.exists() and completed_result.is_file():
        payload["status"] = "completed"
        payload["result_package_path"] = str(completed_result)
        if completed_status.exists() and completed_status.is_file():
            payload["completed_status_path"] = str(completed_status)
        write_json(_cloud_status_path(root, job_id), payload)
        return payload
    if failed_error.exists() and failed_error.is_file():
        payload["status"] = "failed"
        payload["failed_error_path"] = str(failed_error)
        if failed_log.exists() and failed_log.is_file():
            payload["failed_log_path"] = str(failed_log)
        try:
            failed_payload = read_json(failed_error)
            payload["error"] = failed_payload.get("error")
        except Exception:
            payload["error"] = "Cloud worker failed."
        write_json(_cloud_status_path(root, job_id), payload)
        return payload
    if processing_status.exists() and processing_status.is_file():
        payload["status"] = "processing"
    elif processing_package.exists() and processing_package.is_file():
        payload["status"] = "processing"
    elif incoming_package.exists() and incoming_package.is_file():
        payload["status"] = "sent_to_cloud"
    else:
        payload["status"] = "result_not_ready"
    write_json(_cloud_status_path(root, job_id), payload)
    return payload


def _reset_runtime_paths(props) -> None:
    props.job_package_path = ""
    props.result_package_path = ""
    props.candidate_path = ""
    props.accepted_model_path = ""
    if hasattr(props, "cloud_result_package_path"):
        props.cloud_result_package_path = ""
    if hasattr(props, "cloud_status"):
        props.cloud_status = "not_configured"


def _reset_session_state(props) -> None:
    props.job_id = ""
    props.version_id = ""
    props.primary_image_path = ""
    props.additional_view_path = ""
    props.prompt = ""
    props.target_size = ""
    _reset_runtime_paths(props)


def _build_self_check_payload(props) -> dict[str, str]:
    return {
        "addon_path": str(Path(__file__).resolve()),
        "build_id": ADDON_BUILD_ID,
        "workspace_root": str(workspace_root()),
        "primary_image_path": _normalize_path_string(getattr(props, "primary_image_path", "")),
        "job_id": str(getattr(props, "job_id", "") or ""),
        "job_package_path": _normalize_path_string(getattr(props, "job_package_path", "")),
        "result_package_path": _normalize_path_string(getattr(props, "result_package_path", "")),
        "candidate_model_path": _normalize_path_string(getattr(props, "candidate_path", "")),
        "accepted_model_path": _normalize_path_string(getattr(props, "accepted_model_path", "")),
    }


def _export_selected_object_to_stl(stl_path: Path, accepted_object) -> None:
    stl_path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(bpy.ops.wm, "stl_export"):
        with bpy.context.temp_override(active_object=accepted_object, object=accepted_object, selected_objects=[accepted_object], selected_editable_objects=[accepted_object]):
            bpy.ops.wm.stl_export(filepath=str(stl_path), export_selected_objects=True, check_existing=False)
        return
    if hasattr(bpy.ops.export_mesh, "stl"):
        with bpy.context.temp_override(active_object=accepted_object, object=accepted_object, selected_objects=[accepted_object], selected_editable_objects=[accepted_object]):
            bpy.ops.export_mesh.stl(filepath=str(stl_path), use_selection=True, check_existing=False)
        return
    raise HY3DError("No STL export operator is available in this Blender build")


if BLENDER_AVAILABLE:  # pragma: no branch
    class HY3DProperties(PropertyGroup):
        input_mode: EnumProperty(
            name="Input Mode",
            items=[("single_image", "Single Image", ""), ("multiple_views", "Multiple Views", "")],
            default="single_image",
        )
        primary_image_path: StringProperty(name="Primary Image", subtype="FILE_PATH")
        additional_view_path: StringProperty(name="Additional View", subtype="FILE_PATH")
        additional_view_type: EnumProperty(
            name="View Type",
            items=[
                ("front", "front", ""),
                ("side", "side", ""),
                ("back", "back", ""),
                ("top", "top", ""),
                ("detail", "detail", ""),
                ("unknown", "unknown", ""),
            ],
            default="unknown",
        )
        prompt: StringProperty(name="Prompt", default="")
        target_size: StringProperty(name="Target Size", default="")
        job_id: StringProperty(name="Job ID", default="")
        version_id: StringProperty(name="Version ID", default="v1")
        job_package_path: StringProperty(name="Job Package Path", default="")
        cloud_root_folder: StringProperty(name="Cloud Root Folder", subtype="DIR_PATH", default=CLOUD_ROOT_WINDOWS_DEFAULT)
        cloud_status: StringProperty(name="Cloud Status", default="not_configured")
        cloud_result_package_path: StringProperty(name="Cloud Result Package", default="")
        result_package_path: StringProperty(name="Result Package", subtype="FILE_PATH")
        candidate_path: StringProperty(name="Candidate Path", default="")
        accepted_model_path: StringProperty(name="Accepted Model Path", default="")
        visual_score: IntProperty(name="Visual Score", default=3, min=0, max=5)
        geometry_score: IntProperty(name="Geometry Score", default=3, min=0, max=5)
        object_similarity: IntProperty(name="Object Similarity", default=3, min=0, max=5)
        holes_or_artifacts: EnumProperty(
            name="Holes / Artifacts",
            items=[("none", "none", ""), ("minor", "minor", ""), ("moderate", "moderate", ""), ("severe", "severe", "")],
            default="none",
        )
        usable_as_base: BoolProperty(name="Usable as Base", default=False)
        repair_needed: EnumProperty(
            name="Repair Needed",
            items=[("none", "none", ""), ("light", "light", ""), ("heavy", "heavy", ""), ("impossible", "impossible", "")],
            default="none",
        )
        review_notes: StringProperty(name="Notes", default="")
        show_cloud_worker: BoolProperty(name="Cloud Worker", default=True)
        show_advanced_input: BoolProperty(name="Advanced Input", default=False)
        show_advanced_review: BoolProperty(name="Advanced Review", default=False)
        show_debug_info: BoolProperty(name="Debug / Version Info", default=False)


    class HY3D_OT_CreateJobPackage(Operator):
        bl_idname = "hy3d_v2.create_job_package"
        bl_label = "Create Job Package"

        def execute(self, context):
            props = context.scene.hy3d_v2
            primary_image, error = _validate_primary_image_for_job_creation(props.primary_image_path)
            if error is not None or primary_image is None:
                self.report({"ERROR"}, error or "Please select a primary image before creating a job.")
                return {"CANCELLED"}
            try:
                manifest = create_job(
                    workspace_root(),
                    primary_image,
                    reference_views=_selected_reference_views(props),
                    prompt=props.prompt or None,
                    input_mode=props.input_mode,
                )
                zip_path = create_job_package(workspace_root(), manifest["job_id"])
                props.job_id = manifest["job_id"]
                props.version_id = "v1"
                _reset_runtime_paths(props)
                props.job_package_path = str(zip_path)
                props.cloud_status = "ready" if _has_valid_cloud_root(props) else "not_configured"
                self.report({"INFO"}, f"Created {zip_path.name}")
                return {"FINISHED"}
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}


    class HY3D_OT_ImportResultPackage(Operator):
        bl_idname = "hy3d_v2.import_result_package"
        bl_label = "Import Result Package"

        def execute(self, context):
            props = context.scene.hy3d_v2
            result_package = _resolve_existing_file(props.result_package_path, suffix=".zip")
            if result_package is None:
                self.report({"ERROR"}, "Please select a valid result_package.zip.")
                return {"CANCELLED"}
            try:
                manifest = import_result_package(
                    workspace_root(),
                    props.job_id,
                    result_package,
                    version_id=props.version_id or "v1",
                )
                props.candidate_path = manifest["candidate_path"]
                props.accepted_model_path = ""
                self.report({"INFO"}, "Candidate imported into job")
                return {"FINISHED"}
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}


    class HY3D_OT_ResetSession(Operator):
        bl_idname = "hy3d_v2.reset_session"
        bl_label = "Reset HY3D Session"

        def execute(self, context):
            props = context.scene.hy3d_v2
            _reset_session_state(props)
            self.report({"INFO"}, "HY3D session reset.")
            return {"FINISHED"}


    class HY3D_OT_UseSampleInput(Operator):
        bl_idname = "hy3d_v2.use_sample_input"
        bl_label = "Use Sample Input"

        def execute(self, context):
            props = context.scene.hy3d_v2
            sample = _sample_input_path()
            if not sample.exists() or not sample.is_file():
                self.report({"ERROR"}, f"Sample input file does not exist: {sample}")
                return {"CANCELLED"}
            props.primary_image_path = str(sample)
            self.report({"INFO"}, "Sample input selected.")
            return {"FINISHED"}


    class HY3D_OT_SelfCheck(Operator):
        bl_idname = "hy3d_v2.self_check"
        bl_label = "HY3D Self Check"

        def execute(self, context):
            props = context.scene.hy3d_v2
            payload = _build_self_check_payload(props)
            print("HY3D_SELF_CHECK_START")
            for key, value in payload.items():
                print(f"{key}={value}")
            print("HY3D_SELF_CHECK_END")
            self.report({"INFO"}, f"HY3D Self Check printed to console. Build {ADDON_BUILD_ID}")
            return {"FINISHED"}


    class HY3D_OT_SendJobToCloud(Operator):
        bl_idname = "hy3d_v2.send_job_to_cloud"
        bl_label = "Send Job to Cloud"

        def execute(self, context):
            props = context.scene.hy3d_v2
            try:
                payload = send_job_to_cloud(workspace_root(), props.job_id, props.cloud_root_folder, version_id=props.version_id or "v1")
                props.cloud_status = payload["status"]
                props.cloud_result_package_path = ""
                self.report({"INFO"}, "Job sent to cloud incoming folder.")
                return {"FINISHED"}
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}


    class HY3D_OT_CheckCloudResults(Operator):
        bl_idname = "hy3d_v2.check_cloud_results"
        bl_label = "Check Cloud Results"

        def execute(self, context):
            props = context.scene.hy3d_v2
            try:
                payload = check_cloud_results(workspace_root(), props.job_id, props.cloud_root_folder)
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
            props.cloud_status = payload.get("status", "result_not_ready")
            props.cloud_result_package_path = payload.get("result_package_path", "")
            if props.cloud_status == "completed" and props.cloud_result_package_path:
                props.result_package_path = props.cloud_result_package_path
                self.report({"INFO"}, "Cloud result package detected.")
                return {"FINISHED"}
            if props.cloud_status == "failed":
                error = payload.get("error") or "Cloud worker failed."
                self.report({"ERROR"}, error)
                return {"CANCELLED"}
            self.report({"INFO"}, "Cloud result not ready yet.")
            return {"CANCELLED"}


    class HY3D_OT_ImportCloudResult(Operator):
        bl_idname = "hy3d_v2.import_cloud_result"
        bl_label = "Import Cloud Result"

        def execute(self, context):
            props = context.scene.hy3d_v2
            cloud_result = _resolve_existing_file(props.cloud_result_package_path, suffix=".zip")
            if cloud_result is None:
                self.report({"ERROR"}, "Cloud result package is not available yet.")
                return {"CANCELLED"}
            props.result_package_path = str(cloud_result)
            return bpy.ops.hy3d_v2.import_result_package()


    class HY3D_OT_OpenCloudFolder(Operator):
        bl_idname = "hy3d_v2.open_cloud_folder"
        bl_label = "Open Cloud Folder"

        def execute(self, context):
            props = context.scene.hy3d_v2
            cloud_root = _resolve_existing_dir(props.cloud_root_folder)
            if cloud_root is None:
                self.report({"ERROR"}, "Cloud root folder is not configured or does not exist.")
                return {"CANCELLED"}
            bpy.ops.wm.path_open(filepath=str(cloud_root))
            return {"FINISHED"}


    class HY3D_OT_ImportCandidateGLB(Operator):
        bl_idname = "hy3d_v2.import_candidate_glb"
        bl_label = "Import Candidate GLB"

        def execute(self, context):
            props = context.scene.hy3d_v2
            candidate = _resolve_existing_file(props.candidate_path, suffix=".glb")
            if candidate is None:
                self.report({"ERROR"}, "No candidate GLB available. Import a result_package.zip first.")
                return {"CANCELLED"}
            try:
                bpy.ops.import_scene.gltf(filepath=str(candidate))
            except RuntimeError as exc:
                self.report({"ERROR"}, f"Failed to import candidate GLB: {exc}")
                return {"CANCELLED"}
            for obj in context.selected_objects:
                obj["hy3d_job_id"] = props.job_id
                obj["hy3d_version_id"] = props.version_id
                obj["hy3d_role"] = "candidate"
                obj["hy3d_source_path"] = str(candidate)
            self.report({"INFO"}, "Candidate GLB imported")
            return {"FINISHED"}


    class HY3D_OT_SaveReview(Operator):
        bl_idname = "hy3d_v2.save_review"
        bl_label = "Save Review"

        def execute(self, context):
            props = context.scene.hy3d_v2
            review = ReviewPayload(
                visual_score=props.visual_score,
                geometry_score=props.geometry_score,
                object_similarity=props.object_similarity,
                holes_or_artifacts=props.holes_or_artifacts,
                usable_as_base=props.usable_as_base,
                repair_needed=props.repair_needed,
                notes=props.review_notes,
            )
            try:
                save_manual_review(workspace_root(), props.job_id, props.version_id, review)
                self.report({"INFO"}, "Review saved")
                return {"FINISHED"}
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}


    class HY3D_OT_UseSelectedAsAccepted(Operator):
        bl_idname = "hy3d_v2.use_selected_as_accepted"
        bl_label = "Use Selected Object as Accepted Model"

        def execute(self, context):
            props = context.scene.hy3d_v2
            obj = context.active_object
            if obj is None:
                self.report({"ERROR"}, "Select one object first")
                return {"CANCELLED"}
            job_dir = _resolve_existing_dir(workspace_root() / "jobs" / props.job_id)
            if job_dir is None:
                self.report({"ERROR"}, "No active job folder available. Create a job package first.")
                return {"CANCELLED"}
            candidate = _resolve_existing_file(props.candidate_path, suffix=".glb")
            if candidate is None:
                self.report({"ERROR"}, "No candidate GLB available. Import a result_package.zip first.")
                return {"CANCELLED"}
            edited_model = _edited_model_path(props)

            def exporter(destination: Path) -> None:
                destination.parent.mkdir(parents=True, exist_ok=True)
                previous_selection = list(context.selected_objects)
                previous_active = context.view_layer.objects.active
                bpy.ops.object.select_all(action="DESELECT")
                obj.select_set(True)
                context.view_layer.objects.active = obj
                bpy.ops.export_scene.gltf(filepath=str(destination), use_selection=True, export_format="GLB")
                obj["hy3d_role"] = "accepted"
                obj["hy3d_job_id"] = props.job_id
                obj["hy3d_version_id"] = props.version_id
                obj["hy3d_source_path"] = props.candidate_path
                bpy.ops.object.select_all(action="DESELECT")
                for previous in previous_selection:
                    previous.select_set(True)
                context.view_layer.objects.active = previous_active

            try:
                if edited_model is not None and obj.get("hy3d_role") == "edited":
                    accepted_path = promote_edited_model_to_accepted(
                        workspace_root(),
                        props.job_id,
                        props.version_id,
                        source_edited_model=edited_model,
                        accepted_object_name=obj.name,
                        source_candidate_path=str(candidate),
                        human_edited=True,
                    )
                else:
                    accepted_path = promote_selected_object_to_accepted(
                        workspace_root(),
                        props.job_id,
                        props.version_id,
                        exporter=exporter,
                        accepted_object_name=obj.name,
                        source_candidate_path=str(candidate),
                        human_edited=True,
                    )
                obj["hy3d_role"] = "accepted"
                obj["hy3d_job_id"] = props.job_id
                obj["hy3d_version_id"] = props.version_id
                obj["hy3d_source_path"] = str(accepted_path)
                props.accepted_model_path = str(accepted_path)
                self.report({"INFO"}, "Accepted GLB exported")
                return {"FINISHED"}
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}


    class HY3D_OT_SaveSelectedAsEditedModel(Operator):
        bl_idname = "hy3d_v2.save_selected_as_edited"
        bl_label = "Save Selected Object as Edited Model"

        def execute(self, context):
            props = context.scene.hy3d_v2
            obj = context.active_object
            if obj is None:
                self.report({"ERROR"}, "Select one object first")
                return {"CANCELLED"}
            job_dir = _resolve_existing_dir(workspace_root() / "jobs" / props.job_id)
            if job_dir is None:
                self.report({"ERROR"}, "No active job folder available. Create a job package first.")
                return {"CANCELLED"}
            candidate = _resolve_existing_file(props.candidate_path, suffix=".glb")
            if candidate is None:
                self.report({"ERROR"}, "No candidate GLB available. Import a result_package.zip first.")
                return {"CANCELLED"}

            def exporter(destination: Path) -> None:
                destination.parent.mkdir(parents=True, exist_ok=True)
                previous_selection = list(context.selected_objects)
                previous_active = context.view_layer.objects.active
                bpy.ops.object.select_all(action="DESELECT")
                obj.select_set(True)
                context.view_layer.objects.active = obj
                bpy.ops.export_scene.gltf(filepath=str(destination), use_selection=True, export_format="GLB")
                obj["hy3d_role"] = "edited"
                obj["hy3d_job_id"] = props.job_id
                obj["hy3d_version_id"] = props.version_id
                bpy.ops.object.select_all(action="DESELECT")
                for previous in previous_selection:
                    previous.select_set(True)
                context.view_layer.objects.active = previous_active

            try:
                edited_path = save_edited_model(
                    workspace_root(),
                    props.job_id,
                    props.version_id,
                    exporter=exporter,
                    edited_object_name=obj.name,
                    source_candidate_path=str(candidate),
                )
                obj["hy3d_source_path"] = str(edited_path)
                self.report({"INFO"}, "Edited GLB exported")
                return {"FINISHED"}
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}


    class HY3D_OT_ExportAcceptedSTL(Operator):
        bl_idname = "hy3d_v2.export_accepted_stl"
        bl_label = "Export STL from Accepted Model"

        def execute(self, context):
            props = context.scene.hy3d_v2
            accepted_model = _resolve_existing_file(props.accepted_model_path, suffix=".glb")
            if accepted_model is None:
                self.report({"ERROR"}, "No accepted model available. Promote an edited Blender object first.")
                return {"CANCELLED"}

            def exporter(_accepted_glb: Path, stl_path: Path) -> None:
                accepted_object = context.active_object
                for obj in bpy.data.objects:
                    if accepted_object is None and obj.get("hy3d_job_id") == props.job_id and obj.get("hy3d_version_id") == props.version_id and obj.get("hy3d_role") == "accepted":
                        accepted_object = obj
                        break
                if accepted_object is None:
                    for obj in bpy.data.objects:
                        if getattr(obj, "type", None) == "MESH":
                            accepted_object = obj
                            break
                if accepted_object is None:
                    try:
                        import trimesh
                    except Exception as exc:
                        raise HY3DError("Load or accept an object in Blender before STL export") from exc
                    mesh = trimesh.load(_accepted_glb, force="mesh")
                    mesh.export(stl_path)
                    return
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

            try:
                stl_path = export_stl_from_accepted(workspace_root(), props.job_id, exporter=exporter)
                self.report({"INFO"}, f"Exported {stl_path.name}")
                return {"FINISHED"}
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}


    class HY3D_OT_OpenJobFolder(Operator):
        bl_idname = "hy3d_v2.open_job_folder"
        bl_label = "Open Job Folder"

        def execute(self, context):
            props = context.scene.hy3d_v2
            job_dir = _resolve_existing_dir(workspace_root() / "jobs" / props.job_id)
            if job_dir is None:
                self.report({"ERROR"}, "No active job folder available. Create a job package first.")
                return {"CANCELLED"}
            bpy.ops.wm.path_open(filepath=str(job_dir))
            return {"FINISHED"}


    class HY3D_OT_OpenAcceptedFolder(Operator):
        bl_idname = "hy3d_v2.open_accepted_folder"
        bl_label = "Open Accepted Folder"

        def execute(self, context):
            props = context.scene.hy3d_v2
            accepted_model = _resolve_existing_file(props.accepted_model_path, suffix=".glb")
            if accepted_model is None:
                self.report({"ERROR"}, "No accepted model available. Promote an edited Blender object first.")
                return {"CANCELLED"}
            accepted_dir = _resolve_existing_dir(accepted_model.parent)
            if accepted_dir is None:
                self.report({"ERROR"}, "Accepted folder is not available.")
                return {"CANCELLED"}
            bpy.ops.wm.path_open(filepath=str(accepted_dir))
            return {"FINISHED"}


    class HY3D_PT_MainPanel(Panel):
        bl_idname = "HY3D_PT_main_panel"
        bl_label = "HY3D v2"
        bl_space_type = "VIEW_3D"
        bl_region_type = "UI"
        bl_category = "HY3D v2"

        def draw(self, context):
            props = context.scene.hy3d_v2
            layout = self.layout
            state = _ui_state(props)

            header = layout.box()
            header.label(text=f"HY3D v2 Build: {ADDON_BUILD_ID}")
            header.operator("hy3d_v2.self_check")
            header.operator("hy3d_v2.reset_session")

            box = layout.box()
            box.label(text=f"State: {state}")

            if state == "no_job":
                box = layout.box()
                box.label(text="Start")
                box.prop(props, "primary_image_path")
                box.operator("hy3d_v2.use_sample_input")
                box.operator("hy3d_v2.create_job_package")

                adv = layout.box()
                adv.prop(props, "show_advanced_input", text="Advanced Input", emboss=False)
                if props.show_advanced_input:
                    adv.prop(props, "input_mode")
                    adv.prop(props, "additional_view_path")
                    adv.prop(props, "additional_view_type")
                    adv.prop(props, "prompt")
                    adv.prop(props, "target_size")

            elif state == "job_created":
                box = layout.box()
                box.label(text="Job Created")
                box.label(text=f"Job ID: {props.job_id}")
                box.label(text=f"Job Package Path: {props.job_package_path or '(none)'}")
                box.operator("hy3d_v2.open_job_folder")

                cloud = layout.box()
                cloud.prop(props, "show_cloud_worker", text="Cloud Worker", emboss=False)
                if props.show_cloud_worker:
                    cloud.prop(props, "cloud_root_folder")
                    cloud.label(text=f"Cloud Status: {props.cloud_status or 'not_configured'}")
                    cloud.label(text=f"Cloud Result Path: {props.cloud_result_package_path or '(none)'}")
                    cloud.operator("hy3d_v2.send_job_to_cloud")
                    cloud.operator("hy3d_v2.check_cloud_results")
                    row = cloud.row()
                    row.enabled = _has_valid_cloud_result_package_path(props)
                    row.operator("hy3d_v2.import_cloud_result")
                    row = cloud.row()
                    row.enabled = _has_valid_cloud_root(props)
                    row.operator("hy3d_v2.open_cloud_folder")

                box.prop(props, "result_package_path")
                box.label(text=f"Result Package Path: {props.result_package_path or '(none)'}")
                row = box.row()
                row.enabled = _has_valid_result_package_path(props)
                row.operator("hy3d_v2.import_result_package")

            elif state == "result_imported":
                box = layout.box()
                box.label(text="Result Imported")
                box.label(text=f"Candidate Path: {props.candidate_path or '(none)'}")
                row = box.row()
                row.enabled = not _ui_disables_candidate_import_without_candidate(props)
                row.operator("hy3d_v2.import_candidate_glb")

            elif state == "candidate_imported":
                box = layout.box()
                box.label(text="Candidate Imported")
                box.label(text=f"Candidate Path: {props.candidate_path or '(none)'}")
                box.prop(props, "visual_score")
                box.prop(props, "geometry_score")
                box.prop(props, "usable_as_base")
                box.prop(props, "review_notes")
                box.operator("hy3d_v2.save_review")
                box.operator("hy3d_v2.save_selected_as_edited")
                box.operator("hy3d_v2.use_selected_as_accepted")

                adv = layout.box()
                adv.prop(props, "show_advanced_review", text="Advanced Review", emboss=False)
                if props.show_advanced_review:
                    adv.prop(props, "object_similarity")
                    adv.prop(props, "holes_or_artifacts")
                    adv.prop(props, "repair_needed")

            elif state == "accepted_created":
                box = layout.box()
                box.label(text="Accepted Created")
                box.label(text=f"Accepted Model Path: {props.accepted_model_path or '(none)'}")
                row = box.row()
                row.enabled = _has_valid_accepted_model_path(props)
                row.operator("hy3d_v2.export_accepted_stl")
                box.operator("hy3d_v2.open_accepted_folder")

            elif state == "stl_exported":
                box = layout.box()
                box.label(text="STL Exported")
                box.label(text=f"Accepted Model Path: {props.accepted_model_path or '(none)'}")
                stl_path = _accepted_stl_path(props)
                box.label(text=f"Accepted STL Path: {str(stl_path) if stl_path else '(none)'}")
                row = box.row()
                row.enabled = _has_valid_accepted_model_path(props)
                row.operator("hy3d_v2.export_accepted_stl")
                box.operator("hy3d_v2.open_accepted_folder")

            debug = layout.box()
            debug.prop(props, "show_debug_info", text="Debug / Version Info", emboss=False)
            if props.show_debug_info:
                debug.label(text=f"Job ID: {props.job_id or '(none)'}")
                debug.label(text=f"Version ID: {props.version_id or '(none)'}")
                debug.label(text=f"UI State: {state}")
                debug.label(text=f"Loaded Add-on Path: {Path(__file__).resolve()}")
                debug.label(text=f"Workspace Root: {workspace_root()}")


    classes = (
        HY3DProperties,
        HY3D_OT_CreateJobPackage,
        HY3D_OT_ImportResultPackage,
        HY3D_OT_ResetSession,
        HY3D_OT_UseSampleInput,
        HY3D_OT_SelfCheck,
        HY3D_OT_SendJobToCloud,
        HY3D_OT_CheckCloudResults,
        HY3D_OT_ImportCloudResult,
        HY3D_OT_OpenCloudFolder,
        HY3D_OT_ImportCandidateGLB,
        HY3D_OT_SaveReview,
        HY3D_OT_SaveSelectedAsEditedModel,
        HY3D_OT_UseSelectedAsAccepted,
        HY3D_OT_ExportAcceptedSTL,
        HY3D_OT_OpenJobFolder,
        HY3D_OT_OpenAcceptedFolder,
        HY3D_PT_MainPanel,
    )


    def register():
        for cls in classes:
            bpy.utils.register_class(cls)
        bpy.types.Scene.hy3d_v2 = bpy.props.PointerProperty(type=HY3DProperties)
        print(f"HY3D v2 add-on registered. Build {ADDON_BUILD_ID}. Path={Path(__file__).resolve()}")


    def unregister():
        del bpy.types.Scene.hy3d_v2
        for cls in reversed(classes):
            bpy.utils.unregister_class(cls)

else:
    classes = ()

    def register():
        return None


    def unregister():
        return None
