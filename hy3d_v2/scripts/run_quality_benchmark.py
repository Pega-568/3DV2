from __future__ import annotations

import argparse
import csv
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hy3d_v2.hy3d_core.job_service import create_job, import_result_package
from hy3d_v2.hy3d_core.utils.files import ensure_dir, read_json, utc_now_iso, write_json

SUMMARY_FIELDS = [
    "input_name",
    "job_id",
    "version_id",
    "candidate_path",
    "repaired_candidate_light_path",
    "repaired_candidate_meshfix_path",
    "repaired_candidate_meshlab_path",
    "mesh_quality_report_path",
    "repair_comparison_report_path",
    "original_exists",
    "light_exists",
    "meshfix_exists",
    "meshlab_exists",
    "original_vertex_count",
    "original_face_count",
    "original_component_count",
    "original_watertight",
    "light_watertight",
    "meshfix_watertight",
    "meshlab_watertight",
    "repair_recommended",
    "warnings",
    "manual_best_candidate",
    "manual_acceptable_status",
    "notes",
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _hy3d_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _default_report_dir() -> Path:
    return _hy3d_root() / "benchmark_reports"


def _default_workspace(report_dir: Path) -> Path:
    return report_dir / "_benchmark_workspace"


def _candidate_bool(value: Any) -> bool:
    return bool(value is True or str(value).lower() == "true")


def _read_json_if_exists(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return read_json(path)


def _relative_or_str(path_value: str | None, base: Path) -> str:
    if not path_value:
        return ""
    path = Path(path_value)
    try:
        return str(path.relative_to(base)).replace("\\", "/")
    except ValueError:
        return str(path)


def _collect_warnings(*reports: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    for report in reports:
        for key in ["warnings", "validation_warnings", "quality_warnings"]:
            values = report.get(key, [])
            if isinstance(values, list):
                warnings.extend(str(value) for value in values)
    return warnings


def collect_benchmark_row(
    input_name: str,
    workspace_root: Path,
    job_id: str,
    version_id: str = "v1",
) -> dict[str, Any]:
    version_dir = workspace_root / "jobs" / job_id / "versions" / version_id
    engine_output_dir = version_dir / "engine_output"
    validation_dir = version_dir / "validation"
    candidate_manifest = _read_json_if_exists(engine_output_dir / "candidate_manifest.json")
    mesh_quality_report_path = validation_dir / "mesh_quality_report.json"
    repair_comparison_report_path = validation_dir / "repair_comparison_report.json"
    mesh_quality = _read_json_if_exists(mesh_quality_report_path)
    repair_comparison = _read_json_if_exists(repair_comparison_report_path)
    candidates = repair_comparison.get("candidates", {})
    original = candidates.get("original", {})
    light = candidates.get("light", {})
    meshfix = candidates.get("meshfix", {})
    meshlab = candidates.get("meshlab", {})

    candidate_path = candidate_manifest.get("candidate_path") or str(engine_output_dir / "model.glb")
    light_path = candidate_manifest.get("repaired_candidate_light_path")
    meshfix_path = candidate_manifest.get("repaired_candidate_meshfix_path")
    meshlab_path = candidate_manifest.get("repaired_candidate_meshlab_path")
    warnings = _collect_warnings(mesh_quality, original, light, meshfix, meshlab)

    return {
        "input_name": input_name,
        "job_id": job_id,
        "version_id": version_id,
        "candidate_path": _relative_or_str(candidate_path, workspace_root),
        "repaired_candidate_light_path": _relative_or_str(light_path, workspace_root),
        "repaired_candidate_meshfix_path": _relative_or_str(meshfix_path, workspace_root),
        "repaired_candidate_meshlab_path": _relative_or_str(meshlab_path, workspace_root),
        "mesh_quality_report_path": _relative_or_str(str(mesh_quality_report_path), workspace_root),
        "repair_comparison_report_path": _relative_or_str(str(repair_comparison_report_path), workspace_root),
        "original_exists": _candidate_bool(original.get("exists")) or Path(candidate_path).exists(),
        "light_exists": _candidate_bool(light.get("exists")) or bool(light_path and Path(light_path).exists()),
        "meshfix_exists": _candidate_bool(meshfix.get("exists")) or bool(meshfix_path and Path(meshfix_path).exists()),
        "meshlab_exists": _candidate_bool(meshlab.get("exists")) or bool(meshlab_path and Path(meshlab_path).exists()),
        "original_vertex_count": original.get("vertex_count", mesh_quality.get("vertex_count")),
        "original_face_count": original.get("face_count", mesh_quality.get("face_count")),
        "original_component_count": original.get("component_count", mesh_quality.get("component_count")),
        "original_watertight": original.get("watertight", mesh_quality.get("watertight")),
        "light_watertight": light.get("watertight"),
        "meshfix_watertight": meshfix.get("watertight"),
        "meshlab_watertight": meshlab.get("watertight"),
        "repair_recommended": bool(candidate_manifest.get("repair_recommended", mesh_quality.get("repair_recommended", False))),
        "warnings": "; ".join(sorted(set(warnings))),
        "manual_best_candidate": "",
        "manual_acceptable_status": "",
        "notes": "",
    }


def write_summary(report_dir: Path, rows: list[dict[str, Any]]) -> dict[str, Path]:
    ensure_dir(report_dir)
    json_path = report_dir / "benchmark_summary.json"
    csv_path = report_dir / "benchmark_summary.csv"
    write_json(
        json_path,
        {
            "generated_at": utc_now_iso(),
            "row_count": len(rows),
            "fields": SUMMARY_FIELDS,
            "rows": rows,
        },
    )
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in SUMMARY_FIELDS})
    return {"json": json_path, "csv": csv_path}


def _prepare_workspace(workspace_root: Path) -> Path:
    ensure_dir(workspace_root)
    ensure_dir(workspace_root / "jobs")
    return workspace_root


def _fixture_assets() -> tuple[Path, Path]:
    assets_dir = _hy3d_root() / "test_assets"
    return assets_dir / "sample_input.png", assets_dir / "result_package_sample.zip"


def run_fixture_benchmark(report_dir: Path | None = None, workspace_root: Path | None = None) -> dict[str, Any]:
    report_dir = report_dir or _default_report_dir()
    workspace_root = _prepare_workspace(workspace_root or _default_workspace(report_dir))
    input_image, result_package = _fixture_assets()
    job_manifest = create_job(workspace_root, input_image)
    import_result_package(workspace_root, job_manifest["job_id"], result_package)
    rows = [collect_benchmark_row("fixture_sample", workspace_root, job_manifest["job_id"])]
    outputs = write_summary(report_dir, rows)
    return {"mode": "fixture", "workspace_root": workspace_root, "report_dir": report_dir, "outputs": outputs, "rows": rows}


def run_packages_benchmark(
    packages_dir: Path,
    report_dir: Path | None = None,
    workspace_root: Path | None = None,
    input_image: Path | None = None,
) -> dict[str, Any]:
    report_dir = report_dir or _default_report_dir()
    workspace_root = _prepare_workspace(workspace_root or _default_workspace(report_dir))
    input_image = input_image or _fixture_assets()[0]
    packages = sorted(packages_dir.glob("*.zip"))
    rows: list[dict[str, Any]] = []
    for result_package in packages:
        job_manifest = create_job(workspace_root, input_image)
        import_result_package(workspace_root, job_manifest["job_id"], result_package)
        rows.append(collect_benchmark_row(result_package.stem, workspace_root, job_manifest["job_id"]))
    outputs = write_summary(report_dir, rows)
    return {"mode": "packages", "workspace_root": workspace_root, "report_dir": report_dir, "outputs": outputs, "rows": rows}


def run_wrapper_benchmark(
    inputs_dir: Path,
    report_dir: Path | None = None,
    workspace_root: Path | None = None,
    enable_wrapper: bool = False,
) -> dict[str, Any]:
    if not enable_wrapper:
        raise RuntimeError("Wrapper mode is disabled by default. Pass --enable-wrapper to run local engine jobs.")
    wrapper = os.environ.get("HY3D_WRAPPER_RUN")
    if not wrapper:
        raise RuntimeError("HY3D_WRAPPER_RUN is required for wrapper mode.")
    report_dir = report_dir or _default_report_dir()
    workspace_root = _prepare_workspace(workspace_root or _default_workspace(report_dir))
    rows: list[dict[str, Any]] = []
    image_paths = sorted(path for path in inputs_dir.iterdir() if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"})
    for image_path in image_paths:
        completed = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", wrapper, "-InputImage", str(image_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            rows.append(
                {
                    **{field: "" for field in SUMMARY_FIELDS},
                    "input_name": image_path.stem,
                    "warnings": f"wrapper_failed: {completed.stderr.strip() or completed.stdout.strip()}",
                }
            )
            continue
        rows.append({**{field: "" for field in SUMMARY_FIELDS}, "input_name": image_path.stem, "notes": "wrapper run completed; import package manually if wrapper output path is custom"})
    outputs = write_summary(report_dir, rows)
    return {"mode": "wrapper", "workspace_root": workspace_root, "report_dir": report_dir, "outputs": outputs, "rows": rows}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run HY3D quality benchmark summaries.")
    parser.add_argument("--mode", choices=["fixture", "packages", "wrapper"], default="fixture")
    parser.add_argument("--packages-dir", type=Path, help="Folder containing result_package.zip files for packages mode.")
    parser.add_argument("--inputs-dir", type=Path, help="Folder containing real images for wrapper mode.")
    parser.add_argument("--input-image", type=Path, help="Input image used to create HY3D jobs for packages mode.")
    parser.add_argument("--report-dir", type=Path, default=_default_report_dir())
    parser.add_argument("--workspace-root", type=Path)
    parser.add_argument("--clean-workspace", action="store_true")
    parser.add_argument("--enable-wrapper", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.clean_workspace and args.workspace_root and args.workspace_root.exists():
        shutil.rmtree(args.workspace_root)
    if args.mode == "fixture":
        result = run_fixture_benchmark(args.report_dir, args.workspace_root)
    elif args.mode == "packages":
        if not args.packages_dir:
            raise SystemExit("--packages-dir is required for packages mode")
        result = run_packages_benchmark(args.packages_dir, args.report_dir, args.workspace_root, args.input_image)
    else:
        if not args.inputs_dir:
            raise SystemExit("--inputs-dir is required for wrapper mode")
        result = run_wrapper_benchmark(args.inputs_dir, args.report_dir, args.workspace_root, args.enable_wrapper)
    print(f"Benchmark mode: {result['mode']}")
    print(f"Rows: {len(result['rows'])}")
    print(f"JSON: {result['outputs']['json']}")
    print(f"CSV: {result['outputs']['csv']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
