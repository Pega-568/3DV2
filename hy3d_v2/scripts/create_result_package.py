from __future__ import annotations

import argparse
import zipfile
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hy3d_v2.hy3d_core.utils.files import write_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result_manifest = {
        "result_package_version": 1,
        "artifacts": [{"path": "model.glb", "artifact_type": "candidate_glb"}],
    }
    temp_manifest = args.output.parent / "result_manifest.json"
    write_json(temp_manifest, result_manifest)
    with zipfile.ZipFile(args.output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(args.model, "model.glb")
        archive.write(temp_manifest, "result_manifest.json")
    temp_manifest.unlink(missing_ok=True)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
