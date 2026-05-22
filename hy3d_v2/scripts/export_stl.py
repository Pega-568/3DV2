from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hy3d_v2.hy3d_core.job_service import export_active_accepted_stl


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()
    output = export_active_accepted_stl(args.root, args.job_id)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
