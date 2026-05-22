from __future__ import annotations

from pathlib import Path

from .hy3d_core.job_service import (
    HY3DError,
    build_job_paths,
    create_job,
    create_job_package,
    export_stl_from_accepted,
    import_result_package,
    promote_selected_object_to_accepted,
    save_manual_review,
)
from .hy3d_core.models import ReviewPayload
from .hy3d_core.utils.files import copy_file, read_json, utc_now_iso, write_json

bl_info = {
    "name": "HY3D v2 Clean",
    "author": "OpenAI Codex",
    "version": (0, 2, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > HY3D v2 Clean",
    "description": "Clean GLB-first local review workflow for HY3D v2",
    "category": "3D View",
}

ADDON_BUILD_ID = "hy3d_v2_clean_20260521_1535_cloud"
SOURCE_PROJECT_ROOT = Path(r"E:\3DV4\hy3d_v2")
SAMPLE_INPUT = SOURCE_PROJECT_ROOT / "test_assets" / "sample_input.png"
SAMPLE_RESULT_PACKAGE = SOURCE_PROJECT_ROOT / "test_assets" / "result_package_sample.zip"
VALID_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".avif", ".bmp"}
CLOUD_ROOT_WINDOWS_DEFAULT = r"G:\Mi unidad\HY3D_V2_CLOUD"
CLOUD_ROOT_COLAB_DEFAULT = "/content/drive/MyDrive/HY3D_V2_CLOUD"
CLOUD_SUBDIRS = ("incoming", "processing", "completed", "failed", "logs", "notebooks")
CLOUD_STATUS_NOT_CONFIGURED = "not_configured"
CLOUD_STATUS_SENT = "sent_to_cloud"
CLOUD_STATUS_PROCESSING = "processing"
CLOUD_STATUS_COMPLETED = "completed"
CLOUD_STATUS_FAILED = "failed"
CLOUD_STATUS_NOT_READY = "result_not_ready"

try:  # pragma: no cover - Blender-only import
    import bpy
    from bpy.props import BoolProperty, PointerProperty, StringProperty
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

    def PointerProperty(**_kwargs):  # type: ignore[misc]
        return None


def workspace_root() -> Path:
    if BLENDER_AVAILABLE:
        base = Path(bpy.utils.user_resource("DATAFILES", path="hy3d_v2_clean_workspace", create=True))
        base.mkdir(parents=True, exist_ok=True)
        return base
    fallback = SOURCE_PROJECT_ROOT.parent / "hy3d_v2_clean_workspace"
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
    if not raw:
        return None
    path = Path(raw)
    if str(path) in {"", "."}:
        return None
    if not path.exists() or not path.is_file():
        return None
    if suffix and path.suffix.lower() != suffix.lower():
        return None
    return path


def _resolve_existing_dir(value) -> Path | None:
    raw = _normalize_path_string(value)
    if not raw:
        return None
    path = Path(raw)
    if str(path) in {"", "."}:
        return None
    if not path.exists() or not path.is_dir():
        return None
    return path


def _validate_primary_image(value) -> tuple[Path | None, str | None]:
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
    if path.suffix.lower() not in VALID_IMAGE_SUFFIXES:
        return None, "Unsupported image format."
    return path, None


def _find_job_dir(job_id: str) -> Path | None:
    return _resolve_existing_dir(workspace_root() / "jobs" / job_id)


def _find_imported_object(job_id: str, role: str):
    if not BLENDER_AVAILABLE:
        return None
    for obj in bpy.data.objects:
        if obj.get("hy3d_job_id") == job_id and obj.get("hy3d_role") == role:
            return obj
    return None


def _has_valid_job_package_path(props) -> bool:
    return _resolve_existing_file(getattr(props, "job_package_path", ""), suffix=".zip") is not None


def _has_valid_candidate_model_path(props) -> bool:
    return _resolve_existing_file(getattr(props, "candidate_model_path", ""), suffix=".glb") is not None


def _has_valid_accepted_model_path(props) -> bool:
    return _resolve_existing_file(getattr(props, "accepted_model_path", ""), suffix=".glb") is not None


def _has_valid_cloud_result_package_path(props) -> bool:
    return _resolve_existing_file(getattr(props, "cloud_result_package_path", ""), suffix=".zip") is not None


def _has_valid_cloud_root(props) -> bool:
    return _resolve_existing_dir(getattr(props, "cloud_root_folder", "")) is not None


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


def _ensure_cloud_directories(cloud_root_value) -> dict[str, Path]:
    cloud_root = _resolve_existing_dir(cloud_root_value)
    if cloud_root is None:
        raise HY3DError("Cloud root folder is not available.")
    directories = {"root": cloud_root}
    for name in CLOUD_SUBDIRS:
        path = cloud_root / name
        path.mkdir(parents=True, exist_ok=True)
        directories[name] = path
    return directories


def _read_local_cloud_status(root: Path, job_id: str) -> dict:
    status_path = _cloud_status_path(root, job_id)
    if not status_path.exists():
        return {"job_id": job_id, "status": CLOUD_STATUS_NOT_CONFIGURED}
    payload = read_json(status_path)
    if not isinstance(payload, dict):
        return {"job_id": job_id, "status": CLOUD_STATUS_NOT_CONFIGURED}
    return payload


def send_job_to_cloud(root: Path, job_id: str, cloud_root_value, version_id: str = "v1") -> dict:
    if not job_id or not build_job_paths(root, job_id).job_dir.exists():
        raise HY3DError("Create a job package first.")
    paths = build_job_paths(root, job_id, version_id=version_id)
    job_package_path = paths.job_dir / "job_package.zip"
    if not job_package_path.exists() or not job_package_path.is_file():
        raise HY3DError("Job package path is not available.")
    directories = _ensure_cloud_directories(cloud_root_value)
    names = _cloud_names(job_id)
    incoming_package = directories["incoming"] / names["job_package"]
    copy_file(job_package_path, incoming_package)
    payload = {
        "job_id": job_id,
        "cloud_root": str(directories["root"]),
        "incoming_package": str(incoming_package),
        "status": CLOUD_STATUS_SENT,
        "sent_at": utc_now_iso(),
        "expected_result_package": names["result_package"],
        "expected_status_json": names["status_json"],
    }
    write_json(_cloud_status_path(root, job_id), payload)
    return payload


def check_cloud_results(root: Path, job_id: str, cloud_root_value) -> dict:
    if not job_id or not build_job_paths(root, job_id).job_dir.exists():
        raise HY3DError("Create a job package first.")
    directories = _ensure_cloud_directories(cloud_root_value)
    names = _cloud_names(job_id)
    result_package = directories["completed"] / names["result_package"]
    completed_status = directories["completed"] / names["status_json"]
    processing_package = directories["processing"] / names["job_package"]
    processing_status = directories["processing"] / names["status_json"]
    incoming_package = directories["incoming"] / names["job_package"]
    failed_error = directories["failed"] / names["error_json"]
    payload = _read_local_cloud_status(root, job_id)
    payload.update(
        {
            "job_id": job_id,
            "cloud_root": str(directories["root"]),
            "expected_result_package": names["result_package"],
            "expected_status_json": names["status_json"],
        }
    )
    if result_package.exists() and result_package.is_file():
        payload["status"] = CLOUD_STATUS_COMPLETED
        payload["result_package_path"] = str(result_package)
        if completed_status.exists() and completed_status.is_file():
            payload["completed_status_path"] = str(completed_status)
        write_json(_cloud_status_path(root, job_id), payload)
        return payload
    if failed_error.exists() and failed_error.is_file():
        failed_payload = read_json(failed_error)
        payload["status"] = CLOUD_STATUS_FAILED
        payload["failed_error_path"] = str(failed_error)
        if isinstance(failed_payload, dict):
            payload["error"] = failed_payload.get("error", "Cloud worker failed.")
        else:
            payload["error"] = "Cloud worker failed."
        write_json(_cloud_status_path(root, job_id), payload)
        return payload
    if processing_package.exists() or processing_status.exists():
        payload["status"] = CLOUD_STATUS_PROCESSING
    elif incoming_package.exists():
        payload["status"] = CLOUD_STATUS_SENT
    else:
        payload["status"] = CLOUD_STATUS_NOT_READY
    write_json(_cloud_status_path(root, job_id), payload)
    return payload


def _build_self_check_payload(props) -> dict[str, str | bool]:
    return {
        "build_id": ADDON_BUILD_ID,
        "addon_path": str(Path(__file__).resolve()),
        "workspace": str(workspace_root()),
        "sample_input_exists": SAMPLE_INPUT.exists(),
        "sample_result_package_exists": SAMPLE_RESULT_PACKAGE.exists(),
        "job_id": str(getattr(props, "job_id", "") or ""),
        "job_package_path": _normalize_path_string(getattr(props, "job_package_path", "")),
        "cloud_root_folder": _normalize_path_string(getattr(props, "cloud_root_folder", "")),
        "cloud_status": str(getattr(props, "cloud_status", "") or ""),
        "cloud_result_package_path": _normalize_path_string(getattr(props, "cloud_result_package_path", "")),
        "candidate_model_path": _normalize_path_string(getattr(props, "candidate_model_path", "")),
        "accepted_model_path": _normalize_path_string(getattr(props, "accepted_model_path", "")),
    }


def _reset_session(props) -> None:
    props.primary_image_path = ""
    props.job_id = ""
    props.version_id = ""
    props.job_package_path = ""
    props.result_package_path = ""
    props.cloud_status = CLOUD_STATUS_NOT_CONFIGURED
    props.cloud_result_package_path = ""
    props.candidate_model_path = ""
    props.accepted_model_path = ""


def _import_result_package_into_session(props, package_path: Path) -> dict:
    manifest = import_result_package(workspace_root(), props.job_id, package_path, version_id=props.version_id or "v1")
    props.result_package_path = str(package_path)
    props.cloud_result_package_path = str(package_path)
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
    class HY3DCleanProperties(PropertyGroup):
        primary_image_path: StringProperty(name="Primary Image Path", default="")
        job_id: StringProperty(name="Job ID", default="")
        version_id: StringProperty(name="Version ID", default="")
        job_package_path: StringProperty(name="Job Package Path", default="")
        result_package_path: StringProperty(name="Result Package Path", default="")
        cloud_root_folder: StringProperty(name="Cloud Root Folder", subtype="DIR_PATH", default=CLOUD_ROOT_WINDOWS_DEFAULT)
        cloud_status: StringProperty(name="Cloud Status", default=CLOUD_STATUS_NOT_CONFIGURED)
        cloud_result_package_path: StringProperty(name="Cloud Result Package", default="")
        candidate_model_path: StringProperty(name="Candidate Model Path", default="")
        accepted_model_path: StringProperty(name="Accepted Model Path", default="")
        show_cloud_worker: BoolProperty(name="Show Cloud Worker", default=True)


    class HY3D_CLEAN_OT_SelfCheck(Operator):
        bl_idname = "hy3d_v2_clean.self_check"
        bl_label = "Self Check"

        def execute(self, context):
            props = context.scene.hy3d_v2_clean
            payload = _build_self_check_payload(props)
            print("HY3D_V2_CLEAN_SELF_CHECK_START")
            for key, value in payload.items():
                print(f"{key}={value}")
            print("HY3D_V2_CLEAN_SELF_CHECK_END")
            self.report({"INFO"}, f"Build {ADDON_BUILD_ID} self-check printed to console.")
            return {"FINISHED"}


    class HY3D_CLEAN_OT_ResetSession(Operator):
        bl_idname = "hy3d_v2_clean.reset_session"
        bl_label = "Reset Session"

        def execute(self, context):
            _reset_session(context.scene.hy3d_v2_clean)
            self.report({"INFO"}, "HY3D v2 Clean session reset.")
            return {"FINISHED"}


    class HY3D_CLEAN_OT_SelectPrimaryImage(Operator):
        bl_idname = "hy3d_v2_clean.select_primary_image"
        bl_label = "Select Primary Image"

        filepath: StringProperty(subtype="FILE_PATH")
        filter_glob: StringProperty(default="*.png;*.jpg;*.jpeg;*.webp;*.avif;*.bmp", options={"HIDDEN"})

        def invoke(self, context, _event):
            self.filepath = context.scene.hy3d_v2_clean.primary_image_path
            context.window_manager.fileselect_add(self)
            return {"RUNNING_MODAL"}

        def execute(self, context):
            props = context.scene.hy3d_v2_clean
            primary_image, error = _validate_primary_image(self.filepath)
            if error is not None or primary_image is None:
                self.report({"ERROR"}, error or "Invalid primary image.")
                return {"CANCELLED"}
            props.primary_image_path = str(primary_image)
            self.report({"INFO"}, "Primary image selected.")
            return {"FINISHED"}


    class HY3D_CLEAN_OT_UseSampleInput(Operator):
        bl_idname = "hy3d_v2_clean.use_sample_input"
        bl_label = "Use Sample Input"

        def execute(self, context):
            props = context.scene.hy3d_v2_clean
            sample = _resolve_existing_file(SAMPLE_INPUT)
            if sample is None:
                self.report({"ERROR"}, f"Sample input file does not exist: {SAMPLE_INPUT}")
                return {"CANCELLED"}
            props.primary_image_path = str(sample)
            self.report({"INFO"}, "Sample input selected.")
            return {"FINISHED"}


    class HY3D_CLEAN_OT_CreateJobPackage(Operator):
        bl_idname = "hy3d_v2_clean.create_job_package"
        bl_label = "Create Job Package"

        def execute(self, context):
            props = context.scene.hy3d_v2_clean
            primary_image, error = _validate_primary_image(props.primary_image_path)
            if error is not None or primary_image is None:
                self.report({"ERROR"}, error or "Please select a primary image before creating a job.")
                return {"CANCELLED"}
            try:
                manifest = create_job(workspace_root(), primary_image)
                job_package = create_job_package(workspace_root(), manifest["job_id"])
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
            props.job_id = manifest["job_id"]
            props.version_id = "v1"
            props.job_package_path = str(job_package)
            props.result_package_path = ""
            props.cloud_status = CLOUD_STATUS_NOT_CONFIGURED if not _has_valid_cloud_root(props) else CLOUD_STATUS_NOT_READY
            props.cloud_result_package_path = ""
            props.candidate_model_path = ""
            props.accepted_model_path = ""
            self.report({"INFO"}, f"Created {job_package.name}")
            return {"FINISHED"}


    class HY3D_CLEAN_OT_SendJobToCloud(Operator):
        bl_idname = "hy3d_v2_clean.send_job_to_cloud"
        bl_label = "Send Job to Cloud"

        def execute(self, context):
            props = context.scene.hy3d_v2_clean
            try:
                payload = send_job_to_cloud(workspace_root(), props.job_id, props.cloud_root_folder, version_id=props.version_id or "v1")
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
            props.cloud_status = payload["status"]
            props.cloud_result_package_path = ""
            self.report({"INFO"}, "Job sent to cloud incoming folder.")
            return {"FINISHED"}


    class HY3D_CLEAN_OT_CheckCloudResults(Operator):
        bl_idname = "hy3d_v2_clean.check_cloud_results"
        bl_label = "Check Cloud Results"

        def execute(self, context):
            props = context.scene.hy3d_v2_clean
            try:
                payload = check_cloud_results(workspace_root(), props.job_id, props.cloud_root_folder)
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
            props.cloud_status = payload.get("status", CLOUD_STATUS_NOT_READY)
            props.cloud_result_package_path = payload.get("result_package_path", "")
            if props.cloud_status == CLOUD_STATUS_COMPLETED and props.cloud_result_package_path:
                props.result_package_path = props.cloud_result_package_path
                self.report({"INFO"}, "Cloud result package is ready.")
                return {"FINISHED"}
            if props.cloud_status == CLOUD_STATUS_FAILED:
                self.report({"ERROR"}, payload.get("error", "Cloud worker failed."))
                return {"CANCELLED"}
            self.report({"INFO"}, f"Cloud status: {props.cloud_status}")
            return {"FINISHED"}


    class HY3D_CLEAN_OT_ImportCloudResult(Operator):
        bl_idname = "hy3d_v2_clean.import_cloud_result"
        bl_label = "Import Cloud Result"

        def execute(self, context):
            props = context.scene.hy3d_v2_clean
            cloud_result = _resolve_existing_file(props.cloud_result_package_path, suffix=".zip")
            if cloud_result is None:
                self.report({"ERROR"}, "Cloud result package path is not available.")
                return {"CANCELLED"}
            try:
                _import_result_package_into_session(props, cloud_result)
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
            props.cloud_status = CLOUD_STATUS_COMPLETED
            self.report({"INFO"}, "Cloud result package imported.")
            return {"FINISHED"}


    class HY3D_CLEAN_OT_OpenCloudFolder(Operator):
        bl_idname = "hy3d_v2_clean.open_cloud_folder"
        bl_label = "Open Cloud Folder"

        def execute(self, context):
            props = context.scene.hy3d_v2_clean
            cloud_root = _resolve_existing_dir(props.cloud_root_folder)
            if cloud_root is None:
                self.report({"ERROR"}, "Cloud root folder is not available.")
                return {"CANCELLED"}
            bpy.ops.wm.path_open(filepath=str(cloud_root))
            return {"FINISHED"}


    class HY3D_CLEAN_OT_ImportSampleResultPackage(Operator):
        bl_idname = "hy3d_v2_clean.import_sample_result_package"
        bl_label = "Import Sample Result Package"

        def execute(self, context):
            props = context.scene.hy3d_v2_clean
            if not props.job_id or _find_job_dir(props.job_id) is None:
                self.report({"ERROR"}, "Create a job package first.")
                return {"CANCELLED"}
            sample_result = _resolve_existing_file(SAMPLE_RESULT_PACKAGE, suffix=".zip")
            if sample_result is None:
                self.report({"ERROR"}, f"Sample result package does not exist: {SAMPLE_RESULT_PACKAGE}")
                return {"CANCELLED"}
            try:
                _import_result_package_into_session(props, sample_result)
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
            self.report({"INFO"}, "Sample result package imported.")
            return {"FINISHED"}


    class HY3D_CLEAN_OT_ImportCandidateGLB(Operator):
        bl_idname = "hy3d_v2_clean.import_candidate_glb"
        bl_label = "Import Candidate GLB"

        def execute(self, context):
            props = context.scene.hy3d_v2_clean
            candidate = _resolve_existing_file(props.candidate_model_path, suffix=".glb")
            if candidate is None:
                self.report({"ERROR"}, "Candidate model path is not available.")
                return {"CANCELLED"}
            existing_names = {obj.name for obj in bpy.data.objects}
            try:
                bpy.ops.import_scene.gltf(filepath=str(candidate))
            except RuntimeError as exc:
                self.report({"ERROR"}, f"Failed to import candidate GLB: {exc}")
                return {"CANCELLED"}
            imported = [obj for obj in context.selected_objects if obj.name not in existing_names] or list(context.selected_objects)
            for obj in imported:
                obj.name = f"HY3D_CLEAN_{props.job_id}_candidate"
                obj["hy3d_job_id"] = props.job_id
                obj["hy3d_role"] = "candidate"
                obj["hy3d_source_path"] = str(candidate)
            self.report({"INFO"}, "Candidate GLB imported.")
            return {"FINISHED"}


    class HY3D_CLEAN_OT_SaveBasicReview(Operator):
        bl_idname = "hy3d_v2_clean.save_basic_review"
        bl_label = "Save Basic Review"

        def execute(self, context):
            props = context.scene.hy3d_v2_clean
            if not props.job_id or _find_job_dir(props.job_id) is None:
                self.report({"ERROR"}, "Create a job package first.")
                return {"CANCELLED"}
            review = ReviewPayload(
                visual_score=3,
                geometry_score=3,
                object_similarity=3,
                holes_or_artifacts="none",
                usable_as_base=True,
                repair_needed="none",
                notes="clean addon smoke review",
            )
            try:
                save_manual_review(workspace_root(), props.job_id, props.version_id or "v1", review)
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
            self.report({"INFO"}, "Basic review saved.")
            return {"FINISHED"}


    class HY3D_CLEAN_OT_AcceptSelectedObject(Operator):
        bl_idname = "hy3d_v2_clean.accept_selected_object"
        bl_label = "Accept Selected Object"

        def execute(self, context):
            props = context.scene.hy3d_v2_clean
            obj = context.active_object
            if obj is None:
                self.report({"ERROR"}, "Select one object first.")
                return {"CANCELLED"}
            if not props.job_id or _find_job_dir(props.job_id) is None:
                self.report({"ERROR"}, "Create a job package first.")
                return {"CANCELLED"}
            candidate = _resolve_existing_file(props.candidate_model_path, suffix=".glb")
            if candidate is None:
                self.report({"ERROR"}, "Import a result package first.")
                return {"CANCELLED"}

            def exporter(destination: Path) -> None:
                destination.parent.mkdir(parents=True, exist_ok=True)
                previous_selection = list(context.selected_objects)
                previous_active = context.view_layer.objects.active
                bpy.ops.object.select_all(action="DESELECT")
                obj.select_set(True)
                context.view_layer.objects.active = obj
                bpy.ops.export_scene.gltf(filepath=str(destination), use_selection=True, export_format="GLB")
                bpy.ops.object.select_all(action="DESELECT")
                for previous in previous_selection:
                    previous.select_set(True)
                context.view_layer.objects.active = previous_active

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
            obj["hy3d_job_id"] = props.job_id
            obj["hy3d_role"] = "accepted"
            obj["hy3d_source_path"] = str(accepted_path)
            props.accepted_model_path = str(accepted_path)
            self.report({"INFO"}, "Accepted GLB exported.")
            return {"FINISHED"}


    class HY3D_CLEAN_OT_ExportAcceptedSTL(Operator):
        bl_idname = "hy3d_v2_clean.export_accepted_stl"
        bl_label = "Export STL From Accepted"

        def execute(self, context):
            props = context.scene.hy3d_v2_clean
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
                    for obj in imported_temporarily:
                        bpy.data.objects.remove(obj, do_unlink=True)

            try:
                stl_path = export_stl_from_accepted(workspace_root(), props.job_id, exporter=exporter)
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
            self.report({"INFO"}, f"Exported {stl_path.name}")
            return {"FINISHED"}


    class HY3D_CLEAN_OT_OpenWorkspaceFolder(Operator):
        bl_idname = "hy3d_v2_clean.open_workspace_folder"
        bl_label = "Open Workspace Folder"

        def execute(self, _context):
            workspace = _resolve_existing_dir(workspace_root())
            if workspace is None:
                self.report({"ERROR"}, "Workspace folder is not available.")
                return {"CANCELLED"}
            bpy.ops.wm.path_open(filepath=str(workspace))
            return {"FINISHED"}


    class HY3D_V2_CLEAN_PT_MainPanel(Panel):
        bl_idname = "HY3D_V2_CLEAN_PT_main_panel"
        bl_label = "HY3D v2 Clean"
        bl_space_type = "VIEW_3D"
        bl_region_type = "UI"
        bl_category = "HY3D v2 Clean"

        def draw(self, context):
            props = context.scene.hy3d_v2_clean
            layout = self.layout
            layout.label(text="HY3D v2 Clean")
            layout.label(text=f"Build ID: {ADDON_BUILD_ID}")
            layout.operator("hy3d_v2_clean.self_check")
            layout.operator("hy3d_v2_clean.reset_session")

            input_box = layout.box()
            input_box.label(text="Input")
            input_box.label(text=f"Primary Image: {props.primary_image_path or '(none)'}")
            input_box.operator("hy3d_v2_clean.select_primary_image")
            input_box.operator("hy3d_v2_clean.use_sample_input")
            input_box.operator("hy3d_v2_clean.create_job_package")

            cloud_box = layout.box()
            cloud_box.label(text="Cloud Worker")
            cloud_box.prop(props, "cloud_root_folder", text="Cloud Root Folder")
            cloud_box.label(text=f"Cloud Status: {props.cloud_status or CLOUD_STATUS_NOT_CONFIGURED}")
            cloud_box.operator("hy3d_v2_clean.send_job_to_cloud")
            cloud_box.operator("hy3d_v2_clean.check_cloud_results")
            row = cloud_box.row()
            row.enabled = _has_valid_cloud_result_package_path(props)
            row.operator("hy3d_v2_clean.import_cloud_result")
            row = cloud_box.row()
            row.enabled = _has_valid_cloud_root(props)
            row.operator("hy3d_v2_clean.open_cloud_folder")

            local_box = layout.box()
            local_box.label(text="Local Test")
            local_box.operator("hy3d_v2_clean.import_sample_result_package")

            candidate_box = layout.box()
            candidate_box.label(text="Candidate")
            row = candidate_box.row()
            row.enabled = _has_valid_candidate_model_path(props)
            row.operator("hy3d_v2_clean.import_candidate_glb")

            review_box = layout.box()
            review_box.label(text="Review")
            review_box.operator("hy3d_v2_clean.save_basic_review")
            review_box.operator("hy3d_v2_clean.accept_selected_object")

            stl_box = layout.box()
            stl_box.label(text="STL")
            row = stl_box.row()
            row.enabled = _has_valid_accepted_model_path(props)
            row.operator("hy3d_v2_clean.export_accepted_stl")

            workspace_box = layout.box()
            workspace_box.label(text="Workspace")
            workspace_box.operator("hy3d_v2_clean.open_workspace_folder")

            info = layout.box()
            info.label(text=f"Job ID: {props.job_id or '(none)'}")
            info.label(text=f"Job Package: {props.job_package_path or '(none)'}")
            info.label(text=f"Cloud Result: {props.cloud_result_package_path or '(none)'}")
            info.label(text=f"Candidate: {props.candidate_model_path or '(none)'}")
            info.label(text=f"Accepted: {props.accepted_model_path or '(none)'}")


    classes = (
        HY3DCleanProperties,
        HY3D_CLEAN_OT_SelfCheck,
        HY3D_CLEAN_OT_ResetSession,
        HY3D_CLEAN_OT_SelectPrimaryImage,
        HY3D_CLEAN_OT_UseSampleInput,
        HY3D_CLEAN_OT_CreateJobPackage,
        HY3D_CLEAN_OT_SendJobToCloud,
        HY3D_CLEAN_OT_CheckCloudResults,
        HY3D_CLEAN_OT_ImportCloudResult,
        HY3D_CLEAN_OT_OpenCloudFolder,
        HY3D_CLEAN_OT_ImportSampleResultPackage,
        HY3D_CLEAN_OT_ImportCandidateGLB,
        HY3D_CLEAN_OT_SaveBasicReview,
        HY3D_CLEAN_OT_AcceptSelectedObject,
        HY3D_CLEAN_OT_ExportAcceptedSTL,
        HY3D_CLEAN_OT_OpenWorkspaceFolder,
        HY3D_V2_CLEAN_PT_MainPanel,
    )


    def register():
        for cls in classes:
            bpy.utils.register_class(cls)
        bpy.types.Scene.hy3d_v2_clean = PointerProperty(type=HY3DCleanProperties)
        print(f"HY3D v2 Clean registered. Build {ADDON_BUILD_ID}. Path={Path(__file__).resolve()}")


    def unregister():
        if hasattr(bpy.types.Scene, "hy3d_v2_clean"):
            del bpy.types.Scene.hy3d_v2_clean
        for cls in reversed(classes):
            bpy.utils.unregister_class(cls)


else:
    classes = ()

    def register():
        return None


    def unregister():
        return None


__all__ = [
    "ADDON_BUILD_ID",
    "CLOUD_ROOT_COLAB_DEFAULT",
    "CLOUD_ROOT_WINDOWS_DEFAULT",
    "CLOUD_STATUS_COMPLETED",
    "CLOUD_STATUS_FAILED",
    "CLOUD_STATUS_NOT_CONFIGURED",
    "CLOUD_STATUS_NOT_READY",
    "CLOUD_STATUS_PROCESSING",
    "CLOUD_STATUS_SENT",
    "CLOUD_SUBDIRS",
    "SAMPLE_INPUT",
    "SAMPLE_RESULT_PACKAGE",
    "VALID_IMAGE_SUFFIXES",
    "_build_self_check_payload",
    "_cloud_names",
    "_cloud_status_path",
    "_ensure_cloud_directories",
    "_has_valid_accepted_model_path",
    "_has_valid_candidate_model_path",
    "_has_valid_cloud_result_package_path",
    "_has_valid_cloud_root",
    "_import_result_package_into_session",
    "_resolve_existing_dir",
    "_resolve_existing_file",
    "_validate_primary_image",
    "bl_info",
    "check_cloud_results",
    "register",
    "send_job_to_cloud",
    "unregister",
    "workspace_root",
]
