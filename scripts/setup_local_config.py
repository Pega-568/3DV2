from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = REPO_ROOT / "hy3d_local_config.example.json"
TARGET = REPO_ROOT / "hy3d_local_config.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or update local HY3D path configuration.")
    parser.add_argument("--force", action="store_true", help="overwrite an existing hy3d_local_config.json")
    parser.add_argument("--project-root")
    parser.add_argument("--engine-root")
    parser.add_argument("--wrapper-run")
    parser.add_argument("--exports-root")
    args = parser.parse_args()

    if TARGET.exists() and not args.force:
        print(f"{TARGET} already exists. Use --force to overwrite.")
        return 0
    if not EXAMPLE.exists():
        raise SystemExit(f"Missing example config: {EXAMPLE}")

    shutil.copy2(EXAMPLE, TARGET)
    payload = json.loads(TARGET.read_text(encoding="utf-8"))
    updates = {
        "HY3D_PROJECT_ROOT": args.project_root,
        "HY3D_ENGINE_ROOT": args.engine_root,
        "HY3D_WRAPPER_RUN": args.wrapper_run,
        "HY3D_EXPORTS_ROOT": args.exports_root,
    }
    for key, value in updates.items():
        if value:
            payload[key] = value
    TARGET.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"Wrote {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
