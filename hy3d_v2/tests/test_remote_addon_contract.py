from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace


LOCAL_CONNECTOR_ROOT = Path(__file__).resolve().parents[2] / "hy3d_local_connector_addon"
if str(LOCAL_CONNECTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(LOCAL_CONNECTOR_ROOT))

import hy3d_local_connector  # noqa: E402


SOURCE = (LOCAL_CONNECTOR_ROOT / "hy3d_local_connector" / "__init__.py").read_text(encoding="utf-8")


def test_addon_declares_local_remote_execution_mode() -> None:
    assert "execution_mode" in SOURCE
    assert '("local", "Local", "")' in SOURCE
    assert '("remote", "Remote", "")' in SOURCE
    assert "remote_server_url" in SOURCE
    assert "remote_job_id" in SOURCE
    assert "remote_status" in SOURCE
    assert "remote_last_error" in SOURCE
    assert hy3d_local_connector._is_remote_mode(SimpleNamespace(execution_mode="remote")) is True
    assert hy3d_local_connector._is_remote_mode(SimpleNamespace(execution_mode="local")) is False


def test_remote_ui_and_operator_contract_exists() -> None:
    for text in [
        "Remote Server",
        "Check Remote Server",
        "Submit Image To Server",
        "Refresh Remote Job Status",
        "Download Original Candidate",
        "Download Light Candidate",
        "Download MeshFix Candidate",
        "Download MeshLab Candidate",
        "Upload Selected As Accepted",
        "Request Remote STL Export",
        "Download Final Package",
    ]:
        assert text in SOURCE

    for operator in [
        "hy3d_local_connector.check_remote_server",
        "hy3d_local_connector.submit_image_to_server",
        "hy3d_local_connector.refresh_remote_job_status",
        "hy3d_local_connector.download_remote_original_candidate",
        "hy3d_local_connector.download_remote_light_candidate",
        "hy3d_local_connector.download_remote_meshfix_candidate",
        "hy3d_local_connector.download_remote_meshlab_candidate",
        "hy3d_local_connector.upload_selected_as_accepted",
        "hy3d_local_connector.request_remote_stl_export",
        "hy3d_local_connector.download_final_package",
    ]:
        assert operator in SOURCE


def test_remote_mode_does_not_call_local_wrapper_from_submit_operator() -> None:
    match = re.search(
        r"class HY3D_LOCAL_CONNECTOR_OT_SubmitImageToServer\(Operator\):(?P<body>.*?)class HY3D_LOCAL_CONNECTOR_OT_RefreshRemoteJobStatus",
        SOURCE,
        flags=re.S,
    )
    assert match is not None
    body = match.group("body")
    assert "WRAPPER_RUN" not in body
    assert "subprocess.run" not in body
    assert "/api/jobs" in body


def test_remote_candidate_metadata_contract() -> None:
    assert 'obj["hy3d_job_id"] = props.job_id' in SOURCE
    assert 'obj["hy3d_remote_job_id"] = job_id' in SOURCE
    assert 'obj["hy3d_role"] = "candidate"' in SOURCE
    assert 'obj["hy3d_candidate_type"] = candidate_type' in SOURCE
    assert 'obj["hy3d_source"] = "remote"' in SOURCE

