from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hy3d_v2.hy3d_core.job_service import create_job, create_job_package
from hy3d_v2.hy3d_core.models import ReferenceView


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--primary-image", type=Path, required=True)
    parser.add_argument("--reference-view", action="append", default=[])
    parser.add_argument("--prompt", default=None)
    args = parser.parse_args()

    views = []
    for item in args.reference_view:
        raw_path, _, view_type = item.partition(":")
        views.append(ReferenceView(path=Path(raw_path), view_type=view_type or "unknown"))

    manifest = create_job(args.root, args.primary_image, reference_views=views, prompt=args.prompt)
    zip_path = create_job_package(args.root, manifest["job_id"])
    print(zip_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
