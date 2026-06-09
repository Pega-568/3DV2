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
        "file_size": stl_path.stat().st_size if stl_path.exists() else 0,
        "readable": False,
        "readable_by_trimesh": False,
        "readable_by_pyvista": False,
        "watertight": None,
        "manifold": None,
        "non_manifold_edges": None,
        "component_count": None,
        "bbox": None,
        "scale_units": "unknown",
        "normal_orientation": "unknown",
        "validation_status": "validation_unavailable",
        "printability_status": "validation_unavailable",
        "validation_warnings": [],
    }
    printability = {
        "status": "validation_unavailable",
        "serious_issues": [],
        "warnings": [],
    }
    if not stl_path.exists():
        report["validation_status"] = "missing_stl"
        report["printability_status"] = "not_printable"
        printability["status"] = "not_printable"
        printability["serious_issues"].append("missing_stl")
        report["printability_report"] = printability
        return report
    if report["file_size"] <= 0:
        report["validation_status"] = "empty_stl"
        report["printability_status"] = "not_printable"
        printability["status"] = "not_printable"
        printability["serious_issues"].append("empty_stl")
        report["printability_report"] = printability
        return report

    try:
        import trimesh

        mesh = trimesh.load(stl_path, force="mesh")
        report["readable"] = True
        report["readable_by_trimesh"] = True
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
        if report["component_count"] == 0:
            printability["status"] = "not_printable"
            printability["serious_issues"].append("empty_mesh")
        elif report["watertight"] and report["manifold"] is True:
            printability["status"] = "print_ready_candidate"
        else:
            printability["status"] = "needs_cleanup"
            printability["serious_issues"].append("mesh_not_watertight")
    except Exception as exc:  # pragma: no cover - environment-specific
        message = f"trimesh_validation_failed: {exc}"
        report["validation_warnings"].append(message)
        printability["warnings"].append(message)

    try:
        import pyvista as pv

        mesh_pv = pv.read(stl_path)
        report["readable"] = True
        report["readable_by_pyvista"] = True
        if report["bbox"] is None:
            bounds = getattr(mesh_pv, "bounds", None)
            if bounds is not None:
                report["bbox"] = [
                    [float(bounds[0]), float(bounds[2]), float(bounds[4])],
                    [float(bounds[1]), float(bounds[3]), float(bounds[5])],
                ]
        if report["component_count"] is None:
            n_cells = getattr(mesh_pv, "n_cells", None)
            if n_cells is not None:
                report["component_count"] = 1 if int(n_cells) > 0 else 0
        if report["validation_status"] != "completed":
            report["validation_status"] = "completed"
    except Exception as exc:  # pragma: no cover - optional dependency
        message = f"pyvista_validation_failed: {exc}"
        report["validation_warnings"].append(message)
        printability["warnings"].append(message)

    if not report["readable"]:
        report["validation_status"] = "validation_unavailable"
        printability["status"] = "validation_unavailable"
    report["printability_status"] = printability["status"]
    report["printability_report"] = printability
    return report
