from __future__ import annotations

import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = PROJECT_ROOT / "hy3d_v2_clean_addon" / "hy3d_v2_clean"
DIST_DIR = PROJECT_ROOT / "dist"
OUTPUT_ZIP = DIST_DIR / "hy3d_v2_clean_addon.zip"

SKIP_DIR_NAMES = {"__pycache__"}
SKIP_SUFFIXES = {".pyc", ".pyo"}


def iter_files():
    for path in PACKAGE_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        yield path


def build_zip() -> Path:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    if OUTPUT_ZIP.exists():
        OUTPUT_ZIP.unlink()
    with zipfile.ZipFile(OUTPUT_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in iter_files():
            archive.write(path, path.relative_to(PACKAGE_ROOT.parent).as_posix())
    return OUTPUT_ZIP


def main() -> int:
    output = build_zip()
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
