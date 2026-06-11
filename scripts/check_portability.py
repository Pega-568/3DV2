from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
_SEP = chr(92)
_COLON = chr(58)
PERSONAL_PATTERNS = (
    "D" + _COLON + _SEP,
    "E" + _COLON + _SEP,
    "C" + _COLON + _SEP + "Users",
    "3D" + "V4",
    "blender" + "." + "exe",
)
SOURCE_SUFFIXES = {".py", ".ps1", ".json", ".md"}
IGNORED_PARTS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "dist",
    "HY3D_EXPORTS",
    "hy3d_local_connector_workspace",
    "hy3d_local_connector_workspace_smoke",
    "hy3d_local_connector_status_smoke",
    "hy3d_local_connector_mesh_gate_smoke",
    "hy3d_v2_clean_workspace",
    "server_workspace",
    "server_exports",
    "model_cache",
    "docker_data",
    "_workspace_clean",
    "_tmp_blender_space_flow",
    "_tmp_triposr_space_smoke",
    "tests",
}


def _is_ignored_path(path: Path) -> bool:
    parts = set(path.relative_to(REPO_ROOT).parts)
    if parts & IGNORED_PARTS:
        return True
    return path.name in {"hy3d_local_config.json", "_tmp_blender_space_flow.py"}


def _scan_personal_paths() -> list[str]:
    findings: list[str] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        if _is_ignored_path(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for index, line in enumerate(text.splitlines(), start=1):
            if any(pattern in line for pattern in PERSONAL_PATTERNS):
                findings.append(f"{path.relative_to(REPO_ROOT)}:{index}: {line.strip()}")
    return findings


def _git_check_ignore(path: str) -> bool:
    result = subprocess.run(["git", "check-ignore", path], cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    return result.returncode == 0


def _check_addon_zip() -> list[str]:
    errors: list[str] = []
    zip_path = REPO_ROOT / "dist" / "hy3d_local_connector_addon.zip"
    if not zip_path.exists():
        return errors
    with zipfile.ZipFile(zip_path, "r") as archive:
        names = archive.namelist()
    if names != ["hy3d_local_connector/__init__.py"]:
        errors.append(f"Addon ZIP contains unexpected files: {names}")
    return errors


def main() -> int:
    errors: list[str] = []
    personal_findings = _scan_personal_paths()
    if personal_findings:
        errors.append("Personal absolute paths found:\n" + "\n".join(personal_findings))
    required = [
        REPO_ROOT / "hy3d_local_config.example.json",
        REPO_ROOT / "tools" / "triposr" / "run_triposr_local.ps1",
        REPO_ROOT / "hy3d_v2" / "hy3d_core" / "config" / "paths.py",
        REPO_ROOT / "hy3d_v2" / "scripts" / "package_blender_local_connector.py",
    ]
    for path in required:
        if not path.exists():
            errors.append(f"Missing required portability file: {path.relative_to(REPO_ROOT)}")
    if not _git_check_ignore("hy3d_local_config.json"):
        errors.append("hy3d_local_config.json is not ignored by Git")
    errors.extend(_check_addon_zip())
    if errors:
        print("\n\n".join(errors))
        return 1
    print("Portability check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
