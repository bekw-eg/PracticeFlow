#!/usr/bin/env python3
"""Fail closed on the repository's container supply-chain invariants.

The checker intentionally emits only file names, line numbers and rule names. It
never prints environment values, so it is safe to run in CI around deployments.
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILES = ("backend/Dockerfile", "backend/Dockerfile.dev", "frontend/Dockerfile", "frontend/Dockerfile.dev", "testing/minio/Dockerfile")
COMPOSE_FILES = (
    "docker-compose.yml",
    "docker-compose.prod.yml",
    "docker-compose.test.yml",
    "docker-compose.e2e.yml",
    "docker-compose.backup-restore.verify.yml",
    "deployment/caddy/docker-compose.caddy.yml",
)
WORKFLOWS = tuple((ROOT / ".github/workflows").glob("*.y*ml"))
DIGEST = re.compile(r"^[^@\s]+@sha256:[0-9a-f]{64}$")
FROM = re.compile(r"^\s*FROM\s+(?:--platform=\S+\s+)?(?P<image>\S+)", re.IGNORECASE)
USER = re.compile(r"^\s*USER\s+(?P<user>\S+)", re.IGNORECASE)
IMAGE = re.compile(r"^\s*image:\s*(?P<image>[^\s#]+)")
USES = re.compile(r"^\s*-\s*uses:\s*(?P<action>[^\s#]+)")
KEY_VALUE = re.compile(r"^\s*(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?P<value>.*)$")
SENSITIVE_KEY = re.compile(r"(?:secret|password|token|api[_-]?key|access[_-]?key|private[_-]?key|credential|dsn)", re.IGNORECASE)
FIXTURE_MARKER = re.compile(r"(?:test|e2e|local|development|not[-_ ]?for[-_ ]?production|verify)", re.IGNORECASE)


def report(errors: list[str], relative_path: str, line_number: int, rule: str) -> None:
    errors.append(f"{relative_path}:{line_number}: {rule}")


def lines(relative_path: str) -> list[str]:
    return (ROOT / relative_path).read_text(encoding="utf-8").splitlines()


def check_dockerfile(relative_path: str, errors: list[str]) -> None:
    users: list[tuple[int, str]] = []
    for number, line in enumerate(lines(relative_path), start=1):
        from_match = FROM.match(line)
        if from_match and not DIGEST.fullmatch(from_match.group("image")):
            report(errors, relative_path, number, "base image must be pinned to an immutable sha256 digest")

        user_match = USER.match(line)
        if user_match:
            user = user_match.group("user").strip('"\'')
            users.append((number, user))
            if user.lower() == "root" or user.split(":", 1)[0] == "0":
                report(errors, relative_path, number, "root USER is forbidden")

        if re.match(r"^\s*(?:ARG|ENV)\s+", line, re.IGNORECASE):
            assignment = re.search(r"\b([A-Za-z_][A-Za-z0-9_]*)=([^\s]+)", line)
            if assignment and SENSITIVE_KEY.search(assignment.group(1)) and not assignment.group(2).startswith("${"):
                report(errors, relative_path, number, "literal sensitive build argument or environment value is forbidden")

    if not users:
        report(errors, relative_path, 1, "final image must declare a non-root USER")
    elif users[-1][1].lower() == "root" or users[-1][1].split(":", 1)[0] == "0":
        report(errors, relative_path, users[-1][0], "final image must run as non-root")

    dockerignore = ROOT / Path(relative_path).parent / ".dockerignore"
    if not dockerignore.is_file() or "*.env" not in dockerignore.read_text(encoding="utf-8"):
        report(errors, relative_path, 1, "build context must exclude all .env files through .dockerignore")


def check_compose(relative_path: str, errors: list[str]) -> None:
    for number, line in enumerate(lines(relative_path), start=1):
        image_match = IMAGE.match(line)
        if image_match:
            image = image_match.group("image")
            if not DIGEST.fullmatch(image):
                report(errors, relative_path, number, "Compose image must be pinned to an immutable sha256 digest")
            if ":latest" in image.lower():
                report(errors, relative_path, number, "latest image tag is forbidden")

        normalized = line.strip().lower()
        if normalized.startswith("privileged:") and normalized.split(":", 1)[1].strip() == "true":
            report(errors, relative_path, number, "privileged Compose service is forbidden")
        if "docker.sock" in normalized:
            report(errors, relative_path, number, "Docker socket mount is forbidden")
        if normalized.startswith("user:"):
            user = normalized.split(":", 1)[1].strip().strip('"\'')
            if user == "root" or user.startswith("0:") or user == "0":
                report(errors, relative_path, number, "root Compose user is forbidden")

        key_value = KEY_VALUE.match(line)
        if key_value and SENSITIVE_KEY.search(key_value.group("key")):
            value = key_value.group("value").strip().strip('"\'')
            if value and not value.startswith("${") and not FIXTURE_MARKER.search(value):
                report(errors, relative_path, number, "literal sensitive Compose value is forbidden")


def check_workflow_pins(errors: list[str]) -> None:
    for workflow in WORKFLOWS:
        relative_path = workflow.relative_to(ROOT).as_posix()
        for number, line in enumerate(workflow.read_text(encoding="utf-8").splitlines(), start=1):
            action_match = USES.match(line)
            if not action_match:
                continue
            action = action_match.group("action")
            if action.startswith("./"):
                continue
            if "@" not in action or not re.fullmatch(r"[0-9a-f]{40}", action.rsplit("@", 1)[1]):
                report(errors, relative_path, number, "GitHub Action must be pinned to a full 40-character commit SHA")


def check_trivy_exceptions(errors: list[str]) -> None:
    relative_path = ".trivyignore"
    exception_file = ROOT / relative_path
    if not exception_file.is_file():
        report(errors, relative_path, 1, "CVE exception file is required")
        return

    previous_comment = ""
    for number, line in enumerate(exception_file.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            previous_comment = stripped.lower()
            continue
        if not re.fullmatch(r"CVE-\d{4}-\d+", stripped, re.IGNORECASE):
            report(errors, relative_path, number, "only CVE identifiers are allowed in the Trivy exception file")
            continue
        metadata = re.search(r"owner=\S+.*expires=(\d{4}-\d{2}-\d{2}).*reason=.+", previous_comment)
        if not metadata:
            report(errors, relative_path, number, "CVE exception requires preceding owner, expires and reason metadata")
            continue
        try:
            expires = date.fromisoformat(metadata.group(1))
        except ValueError:
            report(errors, relative_path, number, "CVE exception expiry must use YYYY-MM-DD")
            continue
        if expires < date.today():
            report(errors, relative_path, number, "CVE exception has expired")


def main() -> int:
    errors: list[str] = []
    for dockerfile in DOCKERFILES:
        check_dockerfile(dockerfile, errors)
    for compose_file in COMPOSE_FILES:
        check_compose(compose_file, errors)
    check_workflow_pins(errors)
    check_trivy_exceptions(errors)

    if errors:
        print("Container supply-chain policy failed:", file=sys.stderr)
        print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1
    print("Container supply-chain policy passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
