from __future__ import annotations

from pathlib import Path


def test_addon_does_not_expose_legacy_routes() -> None:
    addon_source = Path(__file__).resolve().parents[1] / "blender_addon" / "__init__.py"
    content = addon_source.read_text(encoding="utf-8")
    forbidden = [
        "7A",
        "7B",
        "7C",
        "7X",
        "Relief",
        "prefer_3d_if_safe",
        "fallback_mode",
        "volumetric_mode",
    ]
    for item in forbidden:
        assert item not in content


def test_import_cloud_result_reuses_import_result_package_operator() -> None:
    addon_source = Path(__file__).resolve().parents[1] / "blender_addon" / "__init__.py"
    content = addon_source.read_text(encoding="utf-8")
    assert 'return bpy.ops.hy3d_v2.import_result_package()' in content


def test_addon_build_id_is_rendered_in_ui() -> None:
    addon_source = Path(__file__).resolve().parents[1] / "blender_addon" / "__init__.py"
    content = addon_source.read_text(encoding="utf-8")
    assert 'HY3D v2 Build:' in content
