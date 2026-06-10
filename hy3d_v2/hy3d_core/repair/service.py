from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from ..validation.service import validate_candidate_glb

REPAIR_PROFILES = {
    "safe_light": {
        "operations": ["remove_duplicate_faces", "remove_degenerate_faces", "remove_unreferenced_vertices", "merge_vertices", "fix_normals", "fill_holes"],
        "technical_recommendation": "Balanced light repair for review candidates.",
        "warnings": [],
    },
    "visual_preserve": {
        "operations": ["remove_duplicate_faces", "remove_degenerate_faces", "remove_unreferenced_vertices", "merge_vertices", "fix_normals"],
        "technical_recommendation": "Preserves visible structure and avoids hole closing.",
        "warnings": [],
    },
    "printability": {
        "operations": ["remove_duplicate_faces", "remove_degenerate_faces", "remove_unreferenced_vertices", "merge_vertices", "fix_normals", "fill_holes"],
        "technical_recommendation": "Prioritizes watertight/manifold output when possible; manual review remains required.",
        "warnings": ["printability_profile_requires_manual_review"],
    },
    "aggressive_close_holes": {
        "operations": ["remove_duplicate_faces", "remove_degenerate_faces", "remove_unreferenced_vertices", "merge_vertices", "fix_normals", "fill_holes"],
        "technical_recommendation": "Aggressive closing can help printability but may alter real cavities.",
        "warnings": ["aggressive_close_holes_may_close_real_cavities"],
    },
}


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return path


def _profile_config(repair_profile: str) -> dict:
    if repair_profile not in REPAIR_PROFILES:
        raise ValueError(f"Unknown repair profile: {repair_profile}")
    return REPAIR_PROFILES[repair_profile]


def _base_repair_report(candidate_path: Path, backend: str, output_path: Path | None, repair_profile: str) -> dict:
    profile = _profile_config(repair_profile)
    return {
        "backend": backend,
        "repair_profile": repair_profile,
        "candidate_path": str(candidate_path),
        "output_path": str(output_path) if output_path is not None else None,
        "available": False,
        "attempted": False,
        "created": False,
        "repair_recommended": None,
        "operations": [],
        "operations_applied": [],
        "before_metrics": None,
        "after_metrics": None,
        "validation": None,
        "warnings": list(profile["warnings"]),
        "technical_recommendation": profile["technical_recommendation"],
        "no_auto_acceptance": True,
    }


def _load_combined_mesh(candidate_path: Path):
    import trimesh

    scene = trimesh.load(candidate_path, force="scene")
    geometry = getattr(scene, "geometry", None)
    if geometry:
        meshes = [geom for geom in geometry.values() if getattr(geom, "faces", None) is not None]
    elif getattr(scene, "faces", None) is not None:
        meshes = [scene]
    else:
        meshes = []
    if not meshes:
        return None
    if len(meshes) == 1:
        return meshes[0].copy()
    return trimesh.util.concatenate([mesh.copy() for mesh in meshes])


def _export_glb(mesh, output_path: Path) -> None:
    import trimesh

    output_path.parent.mkdir(parents=True, exist_ok=True)
    trimesh.Scene(mesh).export(output_path, file_type="glb")


def _call_if_available(mesh, method_name: str, report: dict) -> None:
    method = getattr(mesh, method_name, None)
    if not callable(method):
        report["warnings"].append(f"{method_name}_unavailable")
        return
    try:
        method()
        report["operations"].append(method_name)
    except Exception as exc:
        report["warnings"].append(f"{method_name}_failed: {exc}")


def repair_with_trimesh_light(candidate_path: Path, output_path: Path, report_path: Path, repair_recommended: bool, repair_profile: str = "safe_light") -> dict:
    report = _base_repair_report(candidate_path, "light", output_path, repair_profile)
    report["available"] = importlib.util.find_spec("trimesh") is not None
    report["repair_recommended"] = repair_recommended
    report["before_metrics"] = validate_candidate_glb(candidate_path) if candidate_path.exists() else None
    if not report["available"]:
        report["warnings"].append("trimesh_unavailable")
        _write_json(report_path, report)
        return report
    if not repair_recommended:
        report["warnings"].append("repair_not_recommended")
        _write_json(report_path, report)
        return report

    report["attempted"] = True
    try:
        mesh = _load_combined_mesh(candidate_path)
        if mesh is None:
            report["warnings"].append("no_mesh_geometry")
            _write_json(report_path, report)
            return report
        for method_name in _profile_config(repair_profile)["operations"]:
            _call_if_available(mesh, method_name, report)
        report["operations_applied"] = list(report["operations"])
        _export_glb(mesh, output_path)
        report["created"] = output_path.exists()
        report["validation"] = validate_candidate_glb(output_path) if output_path.exists() else None
        report["after_metrics"] = report["validation"]
    except Exception as exc:
        report["warnings"].append(f"trimesh_light_repair_failed: {exc}")
    _write_json(report_path, report)
    return report


def repair_with_pymeshfix(candidate_path: Path, output_path: Path, report_path: Path, repair_recommended: bool, repair_profile: str = "safe_light") -> dict:
    report = _base_repair_report(candidate_path, "meshfix", output_path, repair_profile)
    report["available"] = importlib.util.find_spec("pymeshfix") is not None
    report["repair_recommended"] = repair_recommended
    report["before_metrics"] = validate_candidate_glb(candidate_path) if candidate_path.exists() else None
    if not report["available"]:
        report["warnings"].append("pymeshfix_unavailable")
        _write_json(report_path, report)
        return report
    if not repair_recommended:
        report["warnings"].append("repair_not_recommended")
        _write_json(report_path, report)
        return report

    report["attempted"] = True
    try:
        import pymeshfix

        mesh = _load_combined_mesh(candidate_path)
        if mesh is None:
            report["warnings"].append("no_mesh_geometry")
            _write_json(report_path, report)
            return report
        vertices, faces = pymeshfix.clean_from_arrays(mesh.vertices, mesh.faces)
        import trimesh

        repaired = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
        report["operations"].append("pymeshfix.clean_from_arrays")
        report["operations_applied"] = list(report["operations"])
        _export_glb(repaired, output_path)
        report["created"] = output_path.exists()
        report["validation"] = validate_candidate_glb(output_path) if output_path.exists() else None
        report["after_metrics"] = report["validation"]
    except Exception as exc:
        report["warnings"].append(f"pymeshfix_repair_failed: {exc}")
    _write_json(report_path, report)
    return report


def repair_with_pymeshlab(candidate_path: Path, output_path: Path, report_path: Path, repair_recommended: bool, repair_profile: str = "safe_light") -> dict:
    report = _base_repair_report(candidate_path, "meshlab", output_path, repair_profile)
    report["available"] = importlib.util.find_spec("pymeshlab") is not None
    report["repair_recommended"] = repair_recommended
    report["before_metrics"] = validate_candidate_glb(candidate_path) if candidate_path.exists() else None
    if not report["available"]:
        report["warnings"].append("pymeshlab_unavailable")
        _write_json(report_path, report)
        return report
    if not repair_recommended:
        report["warnings"].append("repair_not_recommended")
        _write_json(report_path, report)
        return report

    report["attempted"] = True
    try:
        import pymeshlab
        import trimesh

        mesh = _load_combined_mesh(candidate_path)
        if mesh is None:
            report["warnings"].append("no_mesh_geometry")
            _write_json(report_path, report)
            return report
        temp_dir = output_path.parent / "_meshlab_tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_in = temp_dir / "candidate.ply"
        temp_out = temp_dir / "candidate_repaired.ply"
        mesh.export(temp_in)
        meshset = pymeshlab.MeshSet()
        meshset.load_new_mesh(str(temp_in))
        for method_name in [
            "meshing_remove_duplicate_faces",
            "meshing_remove_duplicate_vertices",
            "meshing_remove_null_faces",
            "meshing_repair_non_manifold_edges",
            "meshing_repair_non_manifold_vertices",
            "meshing_close_holes",
        ]:
            method = getattr(meshset, method_name, None)
            if not callable(method):
                report["warnings"].append(f"{method_name}_unavailable")
                continue
            try:
                method()
                report["operations"].append(method_name)
            except Exception as exc:
                report["warnings"].append(f"{method_name}_failed: {exc}")
        meshset.save_current_mesh(str(temp_out))
        repaired = trimesh.load(temp_out, force="mesh")
        report["operations_applied"] = list(report["operations"])
        _export_glb(repaired, output_path)
        report["created"] = output_path.exists()
        report["validation"] = validate_candidate_glb(output_path) if output_path.exists() else None
        report["after_metrics"] = report["validation"]
    except Exception as exc:
        report["warnings"].append(f"pymeshlab_repair_failed: {exc}")
    _write_json(report_path, report)
    return report


def _comparison_entry(label: str, path: Path | None, repair_report: dict | None = None) -> dict:
    validation = validate_candidate_glb(path) if path is not None and path.exists() else None
    return {
        "label": label,
        "path": str(path) if path is not None else None,
        "exists": bool(path is not None and path.exists()),
        "file_size": path.stat().st_size if path is not None and path.exists() else 0,
        "component_count": validation.get("component_count") if validation else None,
        "watertight": validation.get("watertight") if validation else None,
        "face_count": validation.get("face_count") if validation else None,
        "vertex_count": validation.get("vertex_count") if validation else None,
        "warnings": (validation.get("validation_warnings") if validation else []) + (repair_report.get("warnings", []) if repair_report else []),
    }


def run_repair_benchmark(candidate_path: Path, output_dir: Path, validation_dir: Path, repair_profile: str = "safe_light") -> dict:
    _profile_config(repair_profile)
    output_dir.mkdir(parents=True, exist_ok=True)
    validation_dir.mkdir(parents=True, exist_ok=True)
    original_report = validate_candidate_glb(candidate_path)
    repair_recommended = bool(original_report.get("repair_recommended"))

    light_path = output_dir / "repaired_candidate_light.glb"
    meshfix_path = output_dir / "repaired_candidate_meshfix.glb"
    meshlab_path = output_dir / "repaired_candidate_meshlab.glb"

    light_report = repair_with_trimesh_light(
        candidate_path,
        light_path,
        validation_dir / "repair_report_light.json",
        repair_recommended,
        repair_profile=repair_profile,
    )
    meshfix_report = repair_with_pymeshfix(
        candidate_path,
        meshfix_path,
        validation_dir / "repair_report_meshfix.json",
        repair_recommended,
        repair_profile=repair_profile,
    )
    meshlab_report = repair_with_pymeshlab(
        candidate_path,
        meshlab_path,
        validation_dir / "repair_report_meshlab.json",
        repair_recommended,
        repair_profile=repair_profile,
    )

    comparison = {
        "candidate_path": str(candidate_path),
        "repair_profile": repair_profile,
        "repair_recommended": repair_recommended,
        "operations_applied": {
            "light": light_report.get("operations_applied", []),
            "meshfix": meshfix_report.get("operations_applied", []),
            "meshlab": meshlab_report.get("operations_applied", []),
        },
        "warnings": sorted(set(light_report.get("warnings", []) + meshfix_report.get("warnings", []) + meshlab_report.get("warnings", []))),
        "before_metrics": original_report,
        "after_metrics": {
            "light": light_report.get("after_metrics"),
            "meshfix": meshfix_report.get("after_metrics"),
            "meshlab": meshlab_report.get("after_metrics"),
        },
        "technical_recommendation": _profile_config(repair_profile)["technical_recommendation"],
        "no_auto_acceptance": True,
        "candidates": {
            "original": _comparison_entry("original", candidate_path),
            "light": _comparison_entry("light", light_path, light_report),
            "meshfix": _comparison_entry("meshfix", meshfix_path, meshfix_report),
            "meshlab": _comparison_entry("meshlab", meshlab_path, meshlab_report),
        },
    }
    _write_json(validation_dir / "repair_comparison_report.json", comparison)
    return {
        "repair_profile": repair_profile,
        "repair_recommended": repair_recommended,
        "paths": {
            "light": str(light_path) if light_path.exists() else None,
            "meshfix": str(meshfix_path) if meshfix_path.exists() else None,
            "meshlab": str(meshlab_path) if meshlab_path.exists() else None,
        },
        "report_paths": {
            "light": str(validation_dir / "repair_report_light.json"),
            "meshfix": str(validation_dir / "repair_report_meshfix.json"),
            "meshlab": str(validation_dir / "repair_report_meshlab.json"),
            "comparison": str(validation_dir / "repair_comparison_report.json"),
        },
        "reports": {
            "light": light_report,
            "meshfix": meshfix_report,
            "meshlab": meshlab_report,
            "comparison": comparison,
        },
    }
