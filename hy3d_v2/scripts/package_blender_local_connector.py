from __future__ import annotations

import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = PROJECT_ROOT / "hy3d_local_connector_addon" / "hy3d_local_connector"
DIST_DIR = PROJECT_ROOT / "dist"
OUTPUT_ZIP = DIST_DIR / "hy3d_local_connector_addon.zip"


def build_zip() -> Path:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    if OUTPUT_ZIP.exists():
        OUTPUT_ZIP.unlink()
    with zipfile.ZipFile(OUTPUT_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(PACKAGE_ROOT / "__init__.py", "hy3d_local_connector/__init__.py")
    return OUTPUT_ZIP


def main() -> int:
    output = build_zip()
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
