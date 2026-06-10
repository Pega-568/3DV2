from __future__ import annotations

import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Callable, Iterable

from .models import JobPaths, ReferenceView, ReviewPayload
from .input_quality.service import analyze_input_image
from .repair.service import run_repair_benchmark
from .stl.service import export_glb_to_stl, validate_stl_file
from .utils.files import copy_file, ensure_dir, read_json, utc_now_iso, write_json
from .validation.service import analyze_mesh_quality, validate_candidate_glb

INPUT_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".avif", ".bmp"}


class HY3DError(RuntimeError):
    pass


def _validate_workspace_root(root: Path) -> Path:
    root = Path(root)
    if not str(root).strip() or str(root) == ".":
        raise HY3DError("Workspace root is invalid")
    if not root.exists() or not root.is_dir():
        raise HY3DError(f"Workspace root is invalid: {root}")
    return root


def _new_job_id() -> str:
    return f"job_{uuid.uuid4().hex[:12]}"


def _version_dir(job_dir: Path, version_id: str) -> Path:
    return job_dir / "versions" / version_id


def _is_safe_zip_member(name: str) -> bool:
    normalized = name.replace("\\", "/")
    if not normalized or normalized.endswith("/"):
        return False
    if normalized.startswith("/") or normalized.startswith("../") or "/../" in normalized:
        return False
    if ":" in normalized:
        return False
    return True


def _extract_safe_zip(archive: zipfile.ZipFile, destination: Path) -> list[Path]:
    extracted: list[Path] = []
    for info in archive.infolist():
        if info.is_dir():
            continue
        if not _is_safe_zip_member(info.filename):
            raise HY3DError(f"Unsafe ZIP entry rejected: {info.filename}")
        target = destination / Path(info.filename)
        ensure_dir(target.parent)
        with archive.open(info, "r") as src, target.open("wb") as dst:
            shutil.copyfileobj(src, dst)
        extracted.append(target)
    return extracted


def build_job_paths(root: Path, job_id: str, version_id: str = "v1") -> JobPaths:
    job_dir = root / "jobs" / job_id
    version_dir = _version_dir(job_dir, version_id)
    paths = JobPaths(
        root=root,
        job_dir=job_dir,
        version_dir=version_dir,
        input_dir=job_dir / "input",
        accepted_dir=version_dir / "accepted",
        engine_output_dir=version_dir / "engine_output",
        blender_review_dir=version_dir / "blender_review",
        validation_dir=version_dir / "validation",
        edited_dir=version_dir / "edited",
        multi_view_dir=job_dir / "multi_view",
        instructions_dir=job_dir / "instructions",
    )
    paths.manifests = {
        "job": job_dir / "job_manifest.json",
        "multi_view": paths.multi_view_dir / "multi_view_manifest.json",
        "multi_view_validation": paths.multi_view_dir / "multi_view_validation_report.json",
        "selected_primary": paths.multi_view_dir / "selected_primary_view.json",
        "source_type": version_dir / "source" / "source_type.json",
        "input_quality": paths.validation_dir / "input_quality_report.json",
        "manual_review": paths.blender_review_dir / "manual_review.json",
        "candidate_manifest": paths.engine_output_dir / "candidate_manifest.json",
        "edited_manifest": paths.edited_dir / "edited_manifest.json",
        "accepted_manifest": paths.accepted_dir / "accepted_manifest.json",
        "stl_validation": paths.accepted_dir / "stl_validation_report.json",
        "printability": paths.accepted_dir / "printability_report.json",
    }
    return paths


def _validate_input_image(path: Path) -> None:
    if not path.exists():
        raise HY3DError(f"Missing input image: {path}")
    if path.suffix.lower() not in INPUT_IMAGE_EXTENSIONS:
        raise HY3DError(f"Unsupported input image format: {path.suffix}")


def _copy_reference_views(destination: Path, views: Iterable[ReferenceView]) -> list[dict[str, str]]:
    copied: list[dict[str, str]] = []
    for index, view in enumerate(views, start=1):
        _validate_input_image(view.path)
        dst_name = f"image_{index:02d}{view.path.suffix.lower()}"
        dst = destination / dst_name
        copy_file(view.path, dst)
        copied.append({"path": f"input/original_uploads/{dst_name}", "view_type": view.view_type})
    return copied


def create_job(
    root: Path,
    primary_image: Path,
    reference_views: Iterable[ReferenceView] | None = None,
    prompt: str | None = None,
    input_mode: str = "single_image",
) -> dict:
    root = _validate_workspace_root(root)
    reference_views = list(reference_views or [])
    _validate_input_image(primary_image)

    job_id = _new_job_id()
    paths = build_job_paths(root, job_id)
    for path in [
        paths.job_dir,
        paths.input_dir / "original_uploads",
        paths.multi_view_dir,
        paths.instructions_dir,
        paths.version_dir / "source",
        paths.engine_output_dir,
        paths.validation_dir,
        paths.blender_review_dir / "screenshots",
        paths.edited_dir,
        paths.accepted_dir,
    ]:
        ensure_dir(path)

    primary_dst = copy_file(primary_image, paths.input_dir / f"primary_image{primary_image.suffix.lower()}")
    reference_entries = _copy_reference_views(paths.input_dir / "original_uploads", reference_views)
    input_quality_report = analyze_input_image(primary_dst)
    write_json(paths.manifests["input_quality"], input_quality_report)

    if prompt:
        (paths.instructions_dir / "prompt.txt").write_text(prompt, encoding="utf-8")

    source_input_dst = copy_file(primary_dst, paths.version_dir / "source" / primary_dst.name)
    write_json(
        paths.manifests["source_type"],
        {
            "version_id": "v1",
            "source_type": "image_to_3d",
            "input_mode": input_mode,
            "primary_image": str(source_input_dst.relative_to(paths.job_dir)).replace("\\", "/"),
            "input_quality_report_path": str(paths.manifests["input_quality"].relative_to(paths.job_dir)).replace("\\", "/"),
        },
    )

    job_manifest = {
        "job_id": job_id,
        "created_at": utc_now_iso(),
        "status": "awaiting_external_generation",
        "active_version": "v1",
        "active_accepted_version": None,
        "input_quality_status": input_quality_report.get("input_quality_status"),
        "input_quality_warnings": input_quality_report.get("warnings", []),
        "input_quality_report_path": str(paths.manifests["input_quality"]),
        "versions": [
            {
                "version_id": "v1",
                "source_type": "image_to_3d",
                "status": "awaiting_external_generation",
            }
        ],
    }
    write_json(paths.manifests["job"], job_manifest)

    multi_view_manifest = {
        "job_id": job_id,
        "input_mode": input_mode,
        "primary_image": f"input/{primary_dst.name}",
        "reference_views": reference_entries,
    }
    write_json(paths.manifests["multi_view"], multi_view_manifest)
    write_json(
        paths.manifests["multi_view_validation"],
        {
            "image_count": 1 + len(reference_entries),
            "primary_image": f"input/{primary_dst.name}",
            "reference_views": reference_entries,
            "accepted_for_generation": True,
            "warnings": input_quality_report.get("warnings", []),
        },
    )
    write_json(
        paths.manifests["selected_primary"],
        {
            "selected_primary": f"input/{primary_dst.name}",
            "reason": "user_selected",
        },
    )
    return job_manifest


def _job_package_path(paths: JobPaths) -> Path:
    return paths.job_dir / "job_package.zip"


def create_job_package(root: Path, job_id: str) -> Path:
    root = _validate_workspace_root(root)
    paths = build_job_paths(root, job_id)
    if not paths.job_dir.exists():
        raise HY3DError(f"Unknown job: {job_id}")

    zip_path = _job_package_path(paths)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(paths.manifests["job"], "job_manifest.json")
        for relative in [
            paths.input_dir,
            paths.multi_view_dir,
            paths.instructions_dir,
            paths.version_dir / "source",
        ]:
            if not relative.exists():
                continue
            for file_path in relative.rglob("*"):
                if file_path.is_file():
                    archive.write(file_path, file_path.relative_to(paths.job_dir))
    return zip_path


def _update_version_status(job_manifest: dict, version_id: str, status: str) -> None:
    for version in job_manifest["versions"]:
        if version["version_id"] == version_id:
            version["status"] = status
            break


def import_result_package(root: Path, job_id: str, result_package: Path, version_id: str = "v1", repair_profile: str = "safe_light") -> dict:
    root = _validate_workspace_root(root)
    paths = build_job_paths(root, job_id, version_id)
    if str(result_package).strip() in {"", "."}:
        raise HY3DError("Result package path must be a valid .zip file")
    if result_package.suffix.lower() != ".zip" or not result_package.exists() or not result_package.is_file():
        raise HY3DError("Result package path must be a valid .zip file")

    with zipfile.ZipFile(result_package, "r") as archive:
        extracted = _extract_safe_zip(archive, paths.engine_output_dir)

    result_manifest_path = paths.engine_output_dir / "result_manifest.json"
    if not result_manifest_path.exists():
        raise HY3DError("result_package.zip is missing result_manifest.json")
    try:
        result_manifest = read_json(result_manifest_path)
    except Exception as exc:
        raise HY3DError(f"result_manifest.json is invalid: {exc}") from exc

    candidate_path = paths.engine_output_dir / "model.glb"
    if not candidate_path.exists():
        raise HY3DError("result_package.zip does not contain model.glb")
    if not candidate_path.is_file():
        raise HY3DError("engine_output/model.glb is not a valid file")

    report = validate_candidate_glb(candidate_path)
    mesh_quality_report = analyze_mesh_quality(candidate_path)
    repair_benchmark = run_repair_benchmark(candidate_path, paths.engine_output_dir, paths.validation_dir, repair_profile=repair_profile)
    repaired_candidate_paths = repair_benchmark["paths"]
    repaired_candidate_reports = repair_benchmark["report_paths"]
    candidate_manifest = {
        "job_id": job_id,
        "version_id": version_id,
        "candidate_path": str(candidate_path),
        "repaired_candidate_path": repaired_candidate_paths.get("light"),
        "repaired_candidate_light_path": repaired_candidate_paths.get("light"),
        "repaired_candidate_meshfix_path": repaired_candidate_paths.get("meshfix"),
        "repaired_candidate_meshlab_path": repaired_candidate_paths.get("meshlab"),
        "repaired_candidate_paths": repaired_candidate_paths,
        "imported_at": utc_now_iso(),
        "validation_status": report["validation_status"],
        "mesh_quality_status": "repair_recommended" if mesh_quality_report.get("repair_recommended") else "mesh_ok_or_review",
        "mesh_quality_report_path": str(paths.validation_dir / "mesh_quality_report.json"),
        "repair_report_paths": repaired_candidate_reports,
        "repair_recommended": bool(mesh_quality_report.get("repair_recommended")),
        "repair_profile": repair_benchmark["repair_profile"],
        "result_manifest_path": str(result_manifest_path),
        "result_manifest_version": result_manifest.get("result_package_version"),
        "extracted_files": [str(path) for path in extracted],
    }
    write_json(paths.manifests["candidate_manifest"], candidate_manifest)
    write_json(paths.validation_dir / "candidate_validation_report.json", report)
    write_json(paths.validation_dir / "mesh_quality_report.json", mesh_quality_report)

    job_manifest = read_json(paths.manifests["job"])
    job_manifest["status"] = "candidate_ready_for_review"
    job_manifest["active_version"] = version_id
    _update_version_status(job_manifest, version_id, "candidate")
    write_json(paths.manifests["job"], job_manifest)
    return candidate_manifest


def save_manual_review(root: Path, job_id: str, version_id: str, review: ReviewPayload) -> Path:
    root = _validate_workspace_root(root)
    paths = build_job_paths(root, job_id, version_id)
    warnings: list[str] = []
    if review.usable_as_base and (review.visual_score < 3 or review.geometry_score < 3):
        warnings.append("usable_as_base=true with low scores")
    payload = {
        "job_id": job_id,
        "version_id": version_id,
        "saved_at": utc_now_iso(),
        "warnings": warnings,
        **review.as_dict(),
    }
    return write_json(paths.manifests["manual_review"], payload)


def save_edited_model(
    root: Path,
    job_id: str,
    version_id: str,
    exporter: Callable[[Path], None],
    edited_object_name: str,
    source_candidate_path: str,
) -> Path:
    root = _validate_workspace_root(root)
    paths = build_job_paths(root, job_id, version_id)
    edited_path = paths.edited_dir / "edited_model.glb"
    exporter(edited_path)
    if not edited_path.exists():
        raise HY3DError("Exporter did not create edited_model.glb")
    write_json(
        paths.manifests["edited_manifest"],
        {
            "job_id": job_id,
            "version_id": version_id,
            "edited_model_path": str(edited_path),
            "edited_object_name": edited_object_name,
            "source_candidate_path": source_candidate_path,
            "saved_at": utc_now_iso(),
        },
    )
    return edited_path


def promote_to_accepted(
    root: Path,
    job_id: str,
    version_id: str,
    exporter: Callable[[Path], None],
    accepted_object_name: str,
    source_candidate_path: str,
    human_edited: bool,
) -> Path:
    root = _validate_workspace_root(root)
    paths = build_job_paths(root, job_id, version_id)
    accepted_path = paths.accepted_dir / "accepted_model.glb"
    if accepted_path.exists():
        raise HY3DError("accepted_model.glb already exists for this version")
    exporter(accepted_path)
    if not accepted_path.exists():
        raise HY3DError("Exporter did not create accepted_model.glb")

    manifest = {
        "job_id": job_id,
        "version_id": version_id,
        "source_candidate_path": source_candidate_path,
        "accepted_model_path": str(accepted_path),
        "accepted_object_name": accepted_object_name,
        "human_edited": human_edited,
        "accepted_at": utc_now_iso(),
        "accepted_source": "selected_blender_object",
        "source_type": "selected_object",
    }
    write_json(paths.manifests["accepted_manifest"], manifest)

    job_manifest = read_json(paths.manifests["job"])
    job_manifest["active_version"] = version_id
    job_manifest["active_accepted_version"] = version_id
    job_manifest["status"] = "accepted"
    _update_version_status(job_manifest, version_id, "accepted")
    write_json(paths.manifests["job"], job_manifest)
    return accepted_path


def promote_selected_object_to_accepted(
    root: Path,
    job_id: str,
    version_id: str,
    exporter: Callable[[Path], None],
    accepted_object_name: str,
    source_candidate_path: str,
    human_edited: bool,
) -> Path:
    return promote_to_accepted(
        root=root,
        job_id=job_id,
        version_id=version_id,
        exporter=exporter,
        accepted_object_name=accepted_object_name,
        source_candidate_path=source_candidate_path,
        human_edited=human_edited,
    )


def promote_edited_model_to_accepted(
    root: Path,
    job_id: str,
    version_id: str,
    source_edited_model: Path,
    accepted_object_name: str,
    source_candidate_path: str,
    human_edited: bool,
) -> Path:
    if not source_edited_model.exists() or not source_edited_model.is_file():
        raise HY3DError("edited_model.glb is required before promotion from edited model")

    accepted_path = promote_to_accepted(
        root=root,
        job_id=job_id,
        version_id=version_id,
        exporter=simulate_copy_exporter(source_edited_model),
        accepted_object_name=accepted_object_name,
        source_candidate_path=source_candidate_path,
        human_edited=human_edited,
    )
    accepted_manifest_path = build_job_paths(root, job_id, version_id).manifests["accepted_manifest"]
    accepted_manifest = read_json(accepted_manifest_path)
    accepted_manifest["accepted_source"] = "edited_model_glb"
    accepted_manifest["source_type"] = "edited_model"
    write_json(accepted_manifest_path, accepted_manifest)
    return accepted_path


def create_new_version_from_accepted(root: Path, job_id: str, prompt: str) -> dict:
    root = _validate_workspace_root(root)
    job_manifest = read_json(build_job_paths(root, job_id).manifests["job"])
    source_version = job_manifest.get("active_accepted_version")
    if not source_version:
        raise HY3DError("No accepted version available")

    next_id = f"v{len(job_manifest['versions']) + 1}"
    paths = build_job_paths(root, job_id, next_id)
    for path in [
        paths.version_dir / "source",
        paths.engine_output_dir,
        paths.validation_dir,
        paths.blender_review_dir / "screenshots",
        paths.edited_dir,
        paths.accepted_dir,
    ]:
        ensure_dir(path)

    previous_accepted = build_job_paths(root, job_id, source_version).accepted_dir / "accepted_model.glb"
    if not previous_accepted.exists():
        raise HY3DError("Active accepted version is missing accepted_model.glb")

    copy_file(previous_accepted, paths.version_dir / "source" / "source_model.glb")
    (paths.version_dir / "source" / "modification_prompt.txt").write_text(prompt, encoding="utf-8")
    write_json(
        paths.version_dir / "source" / "source_version.json",
        {
            "version_id": next_id,
            "source_type": "ai_modification_from_glb",
            "source_version": source_version,
        },
    )
    job_manifest["versions"].append(
        {
            "version_id": next_id,
            "source_type": "ai_modification_from_glb",
            "source_version": source_version,
            "status": "awaiting_external_generation",
        }
    )
    job_manifest["active_version"] = next_id
    job_manifest["status"] = "awaiting_external_generation"
    write_json(paths.manifests["job"], job_manifest)
    return {"job_id": job_id, "version_id": next_id, "source_version": source_version}


def export_active_accepted_stl(
    root: Path,
    job_id: str,
    exporter: Callable[[Path, Path], None] | None = None,
) -> Path:
    root = _validate_workspace_root(root)
    base_paths = build_job_paths(root, job_id)
    job_manifest = read_json(base_paths.manifests["job"])
    version_id = job_manifest.get("active_accepted_version")
    if not version_id:
        raise HY3DError("Cannot export STL without an active accepted version")

    paths = build_job_paths(root, job_id, version_id)
    accepted_glb = paths.accepted_dir / "accepted_model.glb"
    if not accepted_glb.exists():
        raise HY3DError("accepted_model.glb is required before STL export")

    stl_path = paths.accepted_dir / "accepted_model.stl"
    export_glb_to_stl(accepted_glb, stl_path, exporter=exporter)
    stl_validation = validate_stl_file(stl_path)
    write_json(paths.manifests["stl_validation"], stl_validation)
    write_json(paths.manifests["printability"], stl_validation["printability_report"])
    return stl_path


def export_stl_from_accepted(
    root: Path,
    job_id: str,
    exporter: Callable[[Path, Path], None] | None = None,
) -> Path:
    return export_active_accepted_stl(root=root, job_id=job_id, exporter=exporter)


def simulate_copy_exporter(source_path: Path) -> Callable[[Path], None]:
    def _exporter(destination: Path) -> None:
        ensure_dir(destination.parent)
        shutil.copy2(source_path, destination)

    return _exporter
