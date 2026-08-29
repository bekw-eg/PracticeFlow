#!/usr/bin/env python3
"""Prove that the disposable test Compose stack is namespace-isolated.

The script creates (but never starts) a PostgreSQL test container under a fresh
project name.  It verifies Docker labels before removing only that generated
project and its own anonymous resources.  It deliberately has no knowledge of
or interaction with the developer's default Compose project.
"""
from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT = f"pf-isolation-{uuid.uuid4().hex[:12]}"
COMPOSE = ["docker", "compose", "--project-name", PROJECT, "-f", "docker-compose.test.yml"]


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=check)


def project_container_ids() -> list[str]:
    result = run("docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={PROJECT}")
    return [item for item in result.stdout.splitlines() if item.strip()]


def main() -> int:
    # A UUID project name must be unused before cleanup is authorized.
    if project_container_ids():
        print(f"Refusing to use unexpectedly occupied Compose project {PROJECT}", file=sys.stderr)
        return 1

    success = False
    try:
        created = run(*COMPOSE, "up", "--no-start", "--no-build", "test-db")
        if created.returncode:
            print(created.stdout, file=sys.stderr)
            return created.returncode

        container_ids = project_container_ids()
        if not container_ids:
            print("Compose isolation check did not create a labeled test container", file=sys.stderr)
            return 1
        labels = run("docker", "inspect", "--format", '{{ index .Config.Labels "com.docker.compose.project" }}', *container_ids)
        if any(label != PROJECT for label in labels.stdout.splitlines()):
            print("Compose isolation labels do not match the generated project name", file=sys.stderr)
            return 1
        print(f"Compose project isolation passed for {PROJECT}; test-db was not started.")
        success = True
        return 0
    finally:
        # This exact UUID was verified absent before creation, so down can only
        # target resources made by this invocation.
        cleanup = run(*COMPOSE, "down", "--volumes", "--remove-orphans", check=False)
        remaining = project_container_ids()
        if cleanup.returncode or remaining:
            print("Failed to clean up the explicitly created isolation project:", file=sys.stderr)
            print(cleanup.stdout, file=sys.stderr)
            if remaining:
                print("Remaining labeled containers: " + ", ".join(remaining), file=sys.stderr)
            if success:
                raise SystemExit(1)


if __name__ == "__main__":
    raise SystemExit(main())
