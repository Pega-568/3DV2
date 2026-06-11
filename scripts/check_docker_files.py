from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
_SEP = chr(92)
_COLON = chr(58)
PERSONAL_PATTERNS = (
    "D" + _COLON + _SEP,
    "E" + _COLON + _SEP,
    "C" + _COLON + _SEP + "Users",
    "/" + "Users" + "/" + "jacur",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _git_check_ignore(path: str) -> bool:
    result = subprocess.run(["git", "check-ignore", path], cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    return result.returncode == 0


def _dockerignore_excludes(path: str) -> bool:
    dockerignore = REPO_ROOT / ".dockerignore"
    if not dockerignore.exists():
        return False
    target = path.replace("\\", "/")
    ignored = False
    for raw_line in dockerignore.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        pattern = line[1:] if negated else line
        pattern = pattern.replace("\\", "/").rstrip("/")
        matched = False
        if pattern.startswith("*.") and target.endswith(pattern[1:]):
            matched = True
        elif pattern.endswith("/"):
            matched = target.startswith(pattern)
        elif "/" not in pattern:
            matched = pattern in target.split("/")
        elif target == pattern or target.startswith(pattern + "/"):
            matched = True
        if matched:
            ignored = not negated
    return ignored


def main() -> int:
    errors: list[str] = []
    required = [
        "docker-compose.yml",
        "docker/api/Dockerfile",
        "docker/scripts/docker-entrypoint-api.sh",
        ".env.docker.example",
        ".dockerignore",
    ]
    for relative in required:
        if not (REPO_ROOT / relative).exists():
            errors.append(f"Missing required Docker file: {relative}")

    if not _git_check_ignore(".env"):
        errors.append(".env is not ignored by Git")
    if _git_check_ignore(".env.docker.example"):
        errors.append(".env.docker.example must be versionable")
    if _dockerignore_excludes("hy3d_v2/test_assets/result_package_sample.zip"):
        errors.append("result_package_sample.zip is excluded from Docker context")

    dockerfile = _read(REPO_ROOT / "docker/api/Dockerfile") if (REPO_ROOT / "docker/api/Dockerfile").exists() else ""
    compose = _read(REPO_ROOT / "docker-compose.yml") if (REPO_ROOT / "docker-compose.yml").exists() else ""
    dockerignore = _read(REPO_ROOT / ".dockerignore") if (REPO_ROOT / ".dockerignore").exists() else ""

    forbidden_dockerfile_tokens = ["COPY server_workspace", "COPY server_exports", "COPY HY3D_EXPORTS", "COPY . /app"]
    for token in forbidden_dockerfile_tokens:
        if token in dockerfile:
            errors.append(f"Dockerfile contains forbidden token: {token}")

    for label, text in {
        "Dockerfile": dockerfile,
        "docker-compose.yml": compose,
        ".dockerignore": dockerignore,
    }.items():
        for pattern in PERSONAL_PATTERNS:
            if pattern in text:
                errors.append(f"{label} contains personal absolute path pattern: {pattern}")

    if "HY3D_SERVER_FIXTURE_RESULT_PACKAGE=hy3d_v2/test_assets/result_package_sample.zip" not in _read(REPO_ROOT / ".env.docker.example"):
        errors.append(".env.docker.example must expose fixture/dev mode")
    if "healthcheck:" not in compose:
        errors.append("docker-compose.yml must define a healthcheck")

    if errors:
        print("\n".join(errors))
        return 1
    print("Docker file check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
