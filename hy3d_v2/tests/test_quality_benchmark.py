from __future__ import annotations

import csv
import shutil
from pathlib import Path

from hy3d_v2.hy3d_core.utils.files import read_json
from hy3d_v2.scripts.run_quality_benchmark import (
    SUMMARY_FIELDS,
    collect_benchmark_row,
    run_fixture_benchmark,
    run_packages_benchmark,
)


ASSETS_DIR = Path(__file__).resolve().parents[1] / "test_assets"


def test_fixture_benchmark_generates_summary_json_and_csv(tmp_path: Path) -> None:
    report_dir = tmp_path / "reports"
    workspace_root = tmp_path / "workspace"

    result = run_fixture_benchmark(report_dir=report_dir, workspace_root=workspace_root)

    json_path = result["outputs"]["json"]
    csv_path = result["outputs"]["csv"]
    assert json_path == report_dir / "benchmark_summary.json"
    assert csv_path == report_dir / "benchmark_summary.csv"
    assert json_path.exists()
    assert csv_path.exists()

    summary = read_json(json_path)
    assert summary["row_count"] == 1
    assert summary["fields"] == SUMMARY_FIELDS
    assert summary["rows"][0]["input_name"] == "fixture_sample"
    assert summary["rows"][0]["candidate_path"].endswith("engine_output/model.glb")
    assert summary["rows"][0]["original_exists"] is True

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["input_name"] == "fixture_sample"
    assert "manual_best_candidate" in rows[0]


def test_packages_benchmark_uses_existing_result_packages_without_engine(tmp_path: Path) -> None:
    packages_dir = tmp_path / "packages"
    packages_dir.mkdir()
    shutil.copy2(ASSETS_DIR / "result_package_sample.zip", packages_dir / "simple_object.zip")

    result = run_packages_benchmark(
        packages_dir=packages_dir,
        report_dir=tmp_path / "reports",
        workspace_root=tmp_path / "workspace",
    )

    assert result["mode"] == "packages"
    assert len(result["rows"]) == 1
    row = result["rows"][0]
    assert row["input_name"] == "simple_object"
    assert row["job_id"].startswith("job_")
    assert row["version_id"] == "v1"
    assert row["mesh_quality_report_path"].endswith("validation/mesh_quality_report.json")
    assert row["repair_comparison_report_path"].endswith("validation/repair_comparison_report.json")


def test_benchmark_rows_are_relative_to_workspace(tmp_path: Path) -> None:
    result = run_fixture_benchmark(report_dir=tmp_path / "reports", workspace_root=tmp_path / "workspace")
    row = collect_benchmark_row("again", result["workspace_root"], result["rows"][0]["job_id"])

    assert row["candidate_path"].startswith("jobs/")
    assert row["mesh_quality_report_path"].startswith("jobs/")
    assert "D:\\" not in row["candidate_path"]
    assert "C:\\" not in row["candidate_path"]


def test_manual_review_template_is_small_and_editable() -> None:
    template_path = Path(__file__).resolve().parents[1] / "benchmark_reports" / "manual_review_template.csv"
    content = template_path.read_text(encoding="utf-8")

    assert "manual_best_candidate" in content
    assert "manual_acceptable_status" in content
    assert "difficult_low_contrast_or_complex_background" in content
