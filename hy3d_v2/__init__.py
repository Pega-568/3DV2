"""HY3D v2 package root and Blender addon entrypoint."""

bl_info = {
    "name": "HY3D v2",
    "author": "OpenAI Codex",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > HY3D v2",
    "description": "GLB-first local review workflow for external 3D generation",
    "category": "3D View",
}

from .blender_addon import register, unregister

__all__ = ["bl_info", "register", "unregister"]
