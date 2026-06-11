from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from hy3d_v2.scripts.package_blender_local_connector import build_zip


REPO_ROOT = Path(__file__).resolve().parents[2]
_SEP = chr(92)
_COLON = chr(58)
PERSONAL_PATTERNS = (
    "D" + _COLON + _SEP,
    "E" + _COLON + _SEP,
    "C" + _COLON + _SEP + "Users",
    "3D" + "V4",
    "blender" + "." + "exe",
)


def test_no_personal_absolute_paths_in_main_source() -> None:
    source_roots = [
        REPO_ROOT / "hy3d_v2" / "hy3d_core",
        REPO_ROOT / "hy3d_v2" / "scripts",
        REPO_ROOT / "hy3d_local_connector_addon" / "hy3d_local_connector",
        REPO_ROOT / "tools",
        REPO_ROOT / "scripts",
    ]
    findings: list[str] = []
    for root in source_roots:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".py", ".ps1", ".md"}:
                continue
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            for index, line in enumerate(text.splitlines(), start=1):
                if any(pattern in line for pattern in PERSONAL_PATTERNS):
                    findings.append(f"{path.relative_to(REPO_ROOT)}:{index}: {line.strip()}")
    assert findings == []


def test_portable_config_example_and_wrapper_exist() -> None:
    assert (REPO_ROOT / "hy3d_local_config.example.json").exists()
    assert (REPO_ROOT / "tools" / "triposr" / "run_triposr_local.ps1").exists()


def test_local_config_is_gitignored() -> None:
    result = subprocess.run(["git", "check-ignore", "hy3d_local_config.json"], cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0


def test_resolver_accepts_relative_paths() -> None:
    from hy3d_v2.hy3d_core.config.paths import resolve_configured_path

    resolved = resolve_configured_path(".\\hy3d_v2", REPO_ROOT)

    assert resolved == REPO_ROOT / "hy3d_v2"


def test_resolver_accepts_environment_variables(monkeypatch) -> None:
    monkeypatch.setenv("HY3D_EXPORTS_ROOT", str(REPO_ROOT / "custom_exports"))
    import hy3d_v2.hy3d_core.config.paths as paths

    reloaded = importlib.reload(paths)

    assert reloaded.get_exports_root() == REPO_ROOT / "custom_exports"


def test_wrapper_reports_clear_error_with_engine_path_containing_spaces(tmp_path: Path) -> None:
    wrapper = REPO_ROOT / "tools" / "triposr" / "run_triposr_local.ps1"
    if not wrapper.exists():
        pytest.skip("portable wrapper is not available")
    input_image = REPO_ROOT / "hy3d_v2" / "test_assets" / "real_smoke_input.png"
    output_dir = tmp_path / "output with spaces"
    engine_root = tmp_path / "3D Models" / "triposr-local"
    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(wrapper),
            "-input_image",
            str(input_image),
            "-output_dir",
            str(output_dir),
            "-job_id",
            "portable_space_test",
            "-version_id",
            "v1",
            "-engine_root",
            str(engine_root),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 9009:
        pytest.skip("PowerShell is not available")

    run_report = output_dir / "run_report.json"
    assert result.returncode != 0
    assert run_report.exists()
    payload = json.loads(run_report.read_text(encoding="utf-8-sig"))
    assert payload["success"] is False
    assert payload["engine_root"] == str(engine_root)
    assert "HY3D_ENGINE_ROOT is not available" in payload["error"]


def test_addon_imports_without_triposr_installed() -> None:
    connector_root = REPO_ROOT / "hy3d_local_connector_addon"
    if str(connector_root) not in sys.path:
        sys.path.insert(0, str(connector_root))
    module = importlib.import_module("hy3d_local_connector")

    status = module._local_engine_status()

    assert isinstance(status["wrapper_exists"], bool)
    assert "recommendation" in status


def test_addon_installed_outside_repo_bootstraps_from_local_config(tmp_path: Path) -> None:
    install_root = tmp_path / "blender_addons"
    addon_dir = install_root / "hy3d_local_connector"
    addon_dir.mkdir(parents=True)
    (addon_dir / "__init__.py").write_text(
        (REPO_ROOT / "hy3d_local_connector_addon" / "hy3d_local_connector" / "__init__.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (install_root / "hy3d_local_config.json").write_text(
        json.dumps(
            {
                "HY3D_PROJECT_ROOT": str(REPO_ROOT / "hy3d_v2"),
                "HY3D_ENGINE_ROOT": str(tmp_path / "missing engine with spaces"),
                "HY3D_WRAPPER_RUN": str(REPO_ROOT / "tools" / "triposr" / "run_triposr_local.ps1"),
                "HY3D_EXPORTS_ROOT": str(tmp_path / "exports"),
            }
        ),
        encoding="utf-8",
    )
    code = (
        "import hy3d_local_connector as h; "
        "s=h._local_engine_status(); "
        "assert s['project_root'].endswith('hy3d_v2'); "
        "assert 'engine_root' in s; "
        "print('ok')"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(install_root)
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout


def test_import_existing_result_package_does_not_depend_on_engine(tmp_path: Path) -> None:
    connector_root = REPO_ROOT / "hy3d_local_connector_addon"
    if str(connector_root) not in sys.path:
        sys.path.insert(0, str(connector_root))
    module = importlib.import_module("hy3d_local_connector")
    workspace = tmp_path / "workspace"
    (workspace / "jobs").mkdir(parents=True)
    engine_output_dir = tmp_path / "engine_output"
    (engine_output_dir / "engine_raw" / "0").mkdir(parents=True)
    input_image = engine_output_dir / "engine_raw" / "0" / "input.png"
    result_package = engine_output_dir / "result_package.zip"
    sample_assets = REPO_ROOT / "hy3d_v2" / "test_assets"
    input_image.write_bytes((sample_assets / "sample_input.png").read_bytes())
    result_package.write_bytes((sample_assets / "result_package_sample.zip").read_bytes())
    props = SimpleNamespace(
        primary_image_path="",
        engine_job_id="",
        job_id="",
        version_id="v1",
        engine_output_dir=str(engine_output_dir),
        local_engine_status_path="",
        result_package_path=str(result_package),
        candidate_model_path="",
        repaired_candidate_path="",
        repaired_candidate_light_path="",
        repaired_candidate_meshfix_path="",
        repaired_candidate_meshlab_path="",
        accepted_model_path="",
        accepted_stl_path="",
        stl_validation_report_path="",
        printability_report_path="",
        exports_dir="",
        current_status=module.STATUS_ENGINE_GENERATED,
        hy3d_imported=False,
        last_status="",
        last_error="",
        input_quality_status="",
        input_quality_warnings="",
        input_quality_report_path="",
        repair_profile="safe_light",
    )

    original_workspace_root = module.workspace_root
    original_engine_root = module.ENGINE_ROOT
    original_wrapper_run = module.WRAPPER_RUN
    try:
        module.workspace_root = lambda: workspace
        module.ENGINE_ROOT = tmp_path / "missing_engine"
        module.WRAPPER_RUN = tmp_path / "missing_wrapper.ps1"
        manifest = module._import_result_package_from_path(props, result_package)
    finally:
        module.workspace_root = original_workspace_root
        module.ENGINE_ROOT = original_engine_root
        module.WRAPPER_RUN = original_wrapper_run

    assert manifest["candidate_path"].endswith("model.glb")
    assert props.job_id.startswith("job_")


def test_addon_zip_contains_only_connector_init() -> None:
    zip_path = build_zip()
    with zipfile.ZipFile(zip_path, "r") as archive:
        names = archive.namelist()

    assert names == ["hy3d_local_connector/__init__.py"]
