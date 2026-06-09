from __future__ import annotations

import json
from pathlib import Path


def _empty_candidate_report(candidate_path: Path) -> dict:
    return {
        "candidate_path": str(candidate_path),
        "exists": candidate_path.exists(),
        "file_size": candidate_path.stat().st_size if candidate_path.exists() else 0,
        "readable_by_trimesh": False,
        "readable_by_pyvista": False,
        "vertex_count": None,
        "face_count": None,
        "bbox": None,
        "component_count": None,
        "watertight": None,
        "winding_consistent": None,
        "euler_number": None,
        "non_empty": False,
        "is_empty": not candidate_path.exists() or candidate_path.stat().st_size == 0,
        "flatness_warning": False,
        "repair_recommended": False,
        "validation_status": "needs_human_review",
        "validation_warnings": [],
    }


def _edge_statistics(mesh) -> tuple[int | None, int | None]:
    try:
        import numpy as np

        counts = np.bincount(mesh.edges_unique_inverse)
        boundary_edges = int((counts == 1).sum())
        non_manifold_edges = int((counts > 2).sum())
        return non_manifold_edges, boundary_edges
    except Exception:
        return None, None


def _flatness_score_from_bbox(bounds) -> float | None:
    if bounds is None:
        return None
    try:
        extents = [abs(float(bounds[1][i]) - float(bounds[0][i])) for i in range(3)]
        longest = max(extents)
        shortest = min(extents)
        if longest <= 0:
            return 0.0
        return round(shortest / longest, 6)
    except Exception:
        return None


def _load_trimesh_scene(candidate_path: Path):
    import trimesh

    return trimesh.load(candidate_path, force="scene")


def _scene_meshes(scene) -> list:
    geometry = getattr(scene, "geometry", None)
    if geometry:
        return [geom for geom in geometry.values() if getattr(geom, "faces", None) is not None]
    if getattr(scene, "faces", None) is not None:
        return [scene]
    return []


def _concatenate_meshes(meshes):
    import trimesh

    if not meshes:
        return None
    if len(meshes) == 1:
        return meshes[0].copy()
    return trimesh.util.concatenate([mesh.copy() for mesh in meshes])


def _export_repaired_candidate(mesh, repaired_candidate_path: Path) -> Path:
    import trimesh

    repaired_candidate_path.parent.mkdir(parents=True, exist_ok=True)
    scene = trimesh.Scene(mesh)
    glb_bytes = scene.export(file_type="glb")
    repaired_candidate_path.write_bytes(glb_bytes)
    return repaired_candidate_path


def _repair_mesh_light(mesh):
    repaired = mesh.copy()
    try:
        repaired.merge_vertices()
    except Exception:
        pass
    try:
        repaired.remove_unreferenced_vertices()
    except Exception:
        pass
    try:
        repaired.fill_holes()
    except Exception:
        pass
    try:
        repaired.process(validate=True)
    except Exception:
        pass
    return repaired


def validate_candidate_glb(candidate_path: Path) -> dict:
    report = _empty_candidate_report(candidate_path)
    if not candidate_path.exists():
        report["validation_status"] = "missing_candidate"
        report["repair_recommended"] = True
        return report

    if report["file_size"] <= 0:
        report["validation_status"] = "empty_candidate"
        report["repair_recommended"] = True
        return report

    try:
        scene = _load_trimesh_scene(candidate_path)
        meshes = _scene_meshes(scene)
        report["readable_by_trimesh"] = True
        bounds = getattr(scene, "bounds", None)
        if bounds is not None:
            report["bbox"] = bounds.tolist()
        report["component_count"] = len(meshes)
        report["non_empty"] = len(meshes) > 0
        report["is_empty"] = len(meshes) == 0
        vertex_total = 0
        face_total = 0
        for geom in meshes:
            vertices = getattr(geom, "vertices", None)
            faces = getattr(geom, "faces", None)
            if vertices is not None:
                vertex_total += len(vertices)
            if faces is not None:
                face_total += len(faces)
        report["vertex_count"] = vertex_total
        report["face_count"] = face_total
        combined = _concatenate_meshes(meshes)
        if combined is not None:
            report["watertight"] = bool(getattr(combined, "is_watertight", False))
            report["winding_consistent"] = bool(getattr(combined, "is_winding_consistent", False))
            try:
                report["euler_number"] = int(combined.euler_number)
            except Exception:
                report["euler_number"] = None
    except Exception as exc:  # pragma: no cover - depends on local stack
        report["validation_warnings"].append(f"trimesh_unavailable_or_failed: {exc}")

    try:
        import pyvista as pv

        _ = pv.read(candidate_path)
        report["readable_by_pyvista"] = True
    except Exception as exc:  # pragma: no cover - optional dependency
        report["validation_warnings"].append(f"pyvista_unavailable_or_failed: {exc}")

    report["repair_recommended"] = bool(
        not report["non_empty"]
        or report["watertight"] is False
        or report["winding_consistent"] is False
        or (report["component_count"] is not None and report["component_count"] > 1)
        or not (report["readable_by_trimesh"] or report["readable_by_pyvista"])
    )
    return report


def analyze_mesh_quality(candidate_path: Path, repaired_candidate_path: Path | None = None) -> dict:
    candidate_report = validate_candidate_glb(candidate_path)
    report = {
        "candidate_path": str(candidate_path),
        "repaired_candidate_path": None,
        "exists": candidate_report["exists"],
        "file_size": candidate_report["file_size"],
        "readable": bool(candidate_report["readable_by_trimesh"] or candidate_report["readable_by_pyvista"]),
        "readable_by_trimesh": candidate_report["readable_by_trimesh"],
        "readable_by_pyvista": candidate_report["readable_by_pyvista"],
        "vertices": candidate_report["vertex_count"],
        "faces": candidate_report["face_count"],
        "vertex_count": candidate_report["vertex_count"],
        "face_count": candidate_report["face_count"],
        "components": candidate_report["component_count"],
        "component_count": candidate_report["component_count"],
        "watertight": candidate_report["watertight"],
        "winding_consistent": candidate_report["winding_consistent"],
        "euler_number": candidate_report["euler_number"],
        "non_empty": candidate_report["non_empty"],
        "non_manifold_edges": None,
        "boundary_edges": None,
        "bbox": candidate_report["bbox"],
        "flatness_score": None,
        "hole_warning": False,
        "disconnected_parts_warning": False,
        "repair_recommended": candidate_report["repair_recommended"],
        "repair_strategy": "none",
        "repair_performed": False,
        "validation_warnings": list(candidate_report["validation_warnings"]),
        "quality_warnings": list(candidate_report["validation_warnings"]),
    }
    if not candidate_path.exists():
        report["quality_warnings"].append("missing_candidate_glb")
        report["repair_recommended"] = True
        report["repair_strategy"] = "manual_review_required"
        return report

    trimesh_meshes = []
    combined_mesh = None
    try:
        scene = _load_trimesh_scene(candidate_path)
        trimesh_meshes = _scene_meshes(scene)
        combined_mesh = _concatenate_meshes(trimesh_meshes)
        report["readable"] = True
        report["components"] = len(trimesh_meshes)
        bounds = getattr(scene, "bounds", None)
        if bounds is not None:
            report["bbox"] = bounds.tolist()
        if combined_mesh is not None:
            report["vertices"] = int(len(combined_mesh.vertices))
            report["faces"] = int(len(combined_mesh.faces))
            report["watertight"] = bool(getattr(combined_mesh, "is_watertight", False))
            non_manifold_edges, boundary_edges = _edge_statistics(combined_mesh)
            report["non_manifold_edges"] = non_manifold_edges
            report["boundary_edges"] = boundary_edges
    except Exception as exc:
        report["quality_warnings"].append(f"trimesh_quality_failed: {exc}")

    try:
        import pyvista as pv

        pv_mesh = pv.read(candidate_path)
        report["readable"] = True
        if report["bbox"] is None:
            bounds = getattr(pv_mesh, "bounds", None)
            if bounds is not None:
                report["bbox"] = [
                    [float(bounds[0]), float(bounds[2]), float(bounds[4])],
                    [float(bounds[1]), float(bounds[3]), float(bounds[5])],
                ]
        if report["components"] is None:
            try:
                connected = pv_mesh.connectivity()
                region_ids = getattr(connected.cell_data, "get", lambda *_args, **_kwargs: None)("RegionId")
                if region_ids is not None:
                    report["components"] = int(len(set(region_ids.tolist())))
            except Exception:
                n_cells = getattr(pv_mesh, "n_cells", None)
                report["components"] = 1 if n_cells and int(n_cells) > 0 else 0
    except Exception as exc:
        report["quality_warnings"].append(f"pyvista_quality_failed: {exc}")

    report["flatness_score"] = _flatness_score_from_bbox(report["bbox"])
    report["hole_warning"] = bool(
        report["watertight"] is False
        or (report["boundary_edges"] is not None and report["boundary_edges"] > 0)
    )
    report["disconnected_parts_warning"] = bool(report["components"] is not None and report["components"] > 1)
    report["repair_recommended"] = bool(
        not report["readable"]
        or report["hole_warning"]
        or report["disconnected_parts_warning"]
        or (report["non_manifold_edges"] is not None and report["non_manifold_edges"] > 0)
    )

    if not report["repair_recommended"]:
        return report

    if repaired_candidate_path is None:
        report["repair_strategy"] = "manual_review_required"
        return report

    if combined_mesh is None:
        report["repair_strategy"] = "manual_review_required"
        return report

    strategy_notes: list[str] = ["trimesh_light_repair"]
    try:
        import importlib.util

        if importlib.util.find_spec("pymeshfix") is None:
            strategy_notes.append("pymeshfix_unavailable")
    except Exception:
        pass

    try:
        repaired_mesh = _repair_mesh_light(combined_mesh)
        _export_repaired_candidate(repaired_mesh, repaired_candidate_path)
        report["repaired_candidate_path"] = str(repaired_candidate_path)
        report["repair_performed"] = True
        report["repair_strategy"] = "+".join(strategy_notes)
    except Exception as exc:
        report["quality_warnings"].append(f"repair_export_failed: {exc}")
        report["repair_strategy"] = "manual_review_required"

    return report


def mesh_quality_report_to_json(report: dict) -> str:
    return json.dumps(report, indent=2, ensure_ascii=True) + "\n"
