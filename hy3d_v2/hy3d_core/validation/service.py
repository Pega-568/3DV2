from __future__ import annotations

from pathlib import Path


def validate_candidate_glb(candidate_path: Path) -> dict:
    report = {
        "candidate_path": str(candidate_path),
        "exists": candidate_path.exists(),
        "file_size": candidate_path.stat().st_size if candidate_path.exists() else 0,
        "readable_by_trimesh": False,
        "readable_by_pyvista": False,
        "vertex_count": None,
        "face_count": None,
        "bbox": None,
        "component_count": None,
        "is_empty": not candidate_path.exists() or candidate_path.stat().st_size == 0,
        "flatness_warning": False,
        "validation_status": "needs_human_review",
        "validation_warnings": [],
    }
    if not candidate_path.exists():
        report["validation_status"] = "missing_candidate"
        return report

    try:
        import trimesh

        mesh = trimesh.load(candidate_path, force="scene")
        report["readable_by_trimesh"] = True
        bounds = getattr(mesh, "bounds", None)
        if bounds is not None:
            report["bbox"] = bounds.tolist()
        geometry = getattr(mesh, "geometry", None)
        if geometry is not None:
            report["component_count"] = len(geometry)
            report["is_empty"] = len(geometry) == 0
            vertex_total = 0
            face_total = 0
            for geom in geometry.values():
                vertices = getattr(geom, "vertices", None)
                faces = getattr(geom, "faces", None)
                if vertices is not None:
                    vertex_total += len(vertices)
                if faces is not None:
                    face_total += len(faces)
            report["vertex_count"] = vertex_total
            report["face_count"] = face_total
    except Exception as exc:  # pragma: no cover - depends on local stack
        report["validation_warnings"].append(f"trimesh_unavailable_or_failed: {exc}")

    try:
        import pyvista as pv

        _ = pv
        report["readable_by_pyvista"] = True
    except Exception as exc:  # pragma: no cover - optional dependency
        report["validation_warnings"].append(f"pyvista_unavailable_or_failed: {exc}")

    return report
