from __future__ import annotations

from pathlib import Path
from typing import Callable


def export_glb_to_stl(
    accepted_glb: Path,
    stl_path: Path,
    exporter: Callable[[Path, Path], None] | None = None,
) -> Path:
    if exporter is not None:
        exporter(accepted_glb, stl_path)
        return stl_path

    try:
        import trimesh
    except Exception as exc:  # pragma: no cover - environment-specific
        raise RuntimeError(f"trimesh is required for non-Blender STL export: {exc}") from exc

    mesh = trimesh.load(accepted_glb, force="mesh")
    mesh.export(stl_path)
    return stl_path


def validate_stl_file(stl_path: Path) -> dict:
    report = {
        "stl_path": str(stl_path),
        "exists": stl_path.exists(),
        "watertight": None,
        "manifold": None,
        "non_manifold_edges": None,
        "component_count": None,
        "bbox": None,
        "scale_units": "unknown",
        "normal_orientation": "unknown",
        "validation_status": "validation_unavailable",
        "printability_status": "validation_unavailable",
    }
    printability = {
        "status": "validation_unavailable",
        "serious_issues": [],
        "warnings": [],
    }
    if not stl_path.exists():
        printability["serious_issues"].append("missing_stl")
        report["printability_report"] = printability
        return report

    try:
        import trimesh

        mesh = trimesh.load(stl_path, force="mesh")
        report["watertight"] = bool(getattr(mesh, "is_watertight", False))
        report["manifold"] = bool(report["watertight"])
        split_meshes = mesh.split(only_watertight=False)
        report["component_count"] = len(split_meshes) if split_meshes is not None else 1
        report["bbox"] = mesh.bounds.tolist()
        try:
            report["non_manifold_edges"] = int(len(mesh.edges_unique) - len(mesh.face_adjacency))
        except Exception:
            report["non_manifold_edges"] = None
        report["validation_status"] = "completed"
        if report["watertight"]:
            printability["status"] = "print_ready_candidate"
        else:
            printability["status"] = "needs_cleanup"
            printability["serious_issues"].append("mesh_not_watertight")
    except Exception as exc:  # pragma: no cover - environment-specific
        printability["warnings"].append(f"trimesh_validation_failed: {exc}")

    report["printability_status"] = printability["status"]
    report["printability_report"] = printability
    return report
