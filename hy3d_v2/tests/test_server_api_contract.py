from __future__ import annotations

import os
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from server.hy3d_api.main import app


ASSETS_DIR = Path(__file__).resolve().parents[1] / "test_assets"


def _client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("HY3D_SERVER_WORKSPACE_ROOT", str(tmp_path / "server_workspace"))
    monkeypatch.setenv("HY3D_SERVER_EXPORTS_ROOT", str(tmp_path / "server_exports"))
    monkeypatch.setenv("HY3D_SERVER_FIXTURE_RESULT_PACKAGE", str(ASSETS_DIR / "result_package_sample.zip"))
    monkeypatch.delenv("HY3D_ENGINE_ROOT", raising=False)
    monkeypatch.delenv("HY3D_WRAPPER_RUN", raising=False)
    return TestClient(app)


def _create_fixture_job(client: TestClient) -> str:
    with (ASSETS_DIR / "real_smoke_input.png").open("rb") as image:
        response = client.post(
            "/api/jobs",
            files={"image": ("real_smoke_input.png", image, "image/png")},
            data={"repair_profile": "safe_light"},
        )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["job_id"].startswith("job_")
    assert payload["status"] == "running"
    return payload["job_id"]


def test_health(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "hy3d-api"}


def test_create_job_status_and_candidate_download(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    job_id = _create_fixture_job(client)

    status = client.get(f"/api/jobs/{job_id}/status")
    assert status.status_code == 200
    assert status.json()["status"] == "candidate_ready_for_review"

    manifest = client.get(f"/api/jobs/{job_id}/manifest")
    assert manifest.status_code == 200
    assert manifest.json()["candidates"]["original"] == "model.glb"
    assert manifest.json()["no_auto_acceptance"] is True

    candidate = client.get(f"/api/jobs/{job_id}/candidates/original")
    assert candidate.status_code == 200
    assert candidate.headers["content-disposition"].endswith('filename="model.glb"')
    assert len(candidate.content) > 0


def test_export_stl_is_blocked_without_accepted_then_uses_accepted(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    job_id = _create_fixture_job(client)

    blocked = client.post(f"/api/jobs/{job_id}/export-stl")
    assert blocked.status_code == 409
    assert "accepted_model.glb" in blocked.text

    with (ASSETS_DIR / "sample_model.glb").open("rb") as accepted:
        accepted_response = client.post(
            f"/api/jobs/{job_id}/accepted",
            files={"accepted_model": ("accepted_model.glb", accepted, "model/gltf-binary")},
            data={"source_candidate_type": "original", "notes": "contract test"},
        )
    assert accepted_response.status_code == 200, accepted_response.text
    assert accepted_response.json()["status"] == "accepted"

    exported = client.post(f"/api/jobs/{job_id}/export-stl")
    assert exported.status_code == 200, exported.text
    assert exported.json()["status"] == "stl_exported"

    workspace = Path(os.environ["HY3D_SERVER_WORKSPACE_ROOT"])
    accepted_dir = workspace / "jobs" / job_id / "versions" / "v1" / "accepted"
    assert (accepted_dir / "accepted_model.glb").exists()
    assert (accepted_dir / "accepted_model.stl").exists()
    assert (accepted_dir / "stl_validation_report.json").exists()
    assert (accepted_dir / "printability_report.json").exists()

    final_package = client.get(f"/api/jobs/{job_id}/final-package")
    assert final_package.status_code == 200
    package_path = tmp_path / "final_package.zip"
    package_path.write_bytes(final_package.content)
    with zipfile.ZipFile(package_path) as archive:
        names = set(archive.namelist())
    assert "accepted_model.glb" in names
    assert "accepted_model.stl" in names
    assert "repair_comparison_report.json" in names
