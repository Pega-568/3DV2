from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_docker_files_contract() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_docker_files.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_docker_compose_has_no_windows_host_paths() -> None:
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "D:\\" not in compose
    assert "E:\\" not in compose
    assert "C:\\Users" not in compose

