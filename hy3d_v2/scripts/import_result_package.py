from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hy3d_v2.hy3d_core.job_service import import_result_package


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--result-package", type=Path, required=True)
    parser.add_argument("--version-id", default="v1")
    args = parser.parse_args()

    manifest = import_result_package(args.root, args.job_id, args.result_package, version_id=args.version_id)
    print(manifest["candidate_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
