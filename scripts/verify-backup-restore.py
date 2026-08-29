#!/usr/bin/env python3
"""Disposable end-to-end verification for the local-volume backup bundle.

It provisions independent source and restore Compose projects, uploads a PNG
through the real API, attaches it to a student report, runs the platform
backup/restore scripts, and verifies the restored image/document/DOCX export.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILE = ROOT / "docker-compose.backup-restore.verify.yml"
SOURCE_PROJECT = "practiceflow_backup_verify_source"
RESTORE_PROJECT = "practiceflow_backup_verify_restore"
SOURCE_PORT = "18080"
RESTORE_PORT = "18081"
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGPUSDnBwMDAxMDAwMDAAAAPegFYAGyRGAAAAABJRU5ErkJggg=="
)


def run(command: list[str], *, env: dict[str, str] | None = None) -> str:
    print("+", " ".join(command), flush=True)
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if completed.returncode:
        print(completed.stdout, end="", file=sys.stderr)
        raise subprocess.CalledProcessError(completed.returncode, command, completed.stdout)
    return completed.stdout or ""


def compose(project: str, *args: str, env: dict[str, str]) -> list[str]:
    return ["docker", "compose", "--project-name", project, "-f", str(COMPOSE_FILE), *args]


def request_json(base_url: str, path: str, *, method: str = "GET", payload: object | None = None, token: str | None = None) -> object:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(f"{base_url}{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def request_bytes(base_url: str, path: str, *, token: str) -> bytes:
    request = urllib.request.Request(f"{base_url}{path}", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def upload_png(base_url: str, token: str) -> dict[str, object]:
    boundary = f"----PracticeFlowBackup{uuid.uuid4().hex}"
    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="file"; filename="backup-verification.png"\r\n',
            b"Content-Type: image/png\r\n\r\n",
            PNG_BYTES,
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )
    request = urllib.request.Request(
        f"{base_url}/api/v1/files",
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"PNG upload failed with HTTP {error.code}: {error.read().decode('utf-8', errors='replace')}") from error


def wait_for_api(base_url: str) -> None:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/health/ready", timeout=3) as response:
                if response.status == 200:
                    return
        except urllib.error.URLError:
            pass
        time.sleep(1)
    raise RuntimeError(f"Timed out waiting for {base_url}")


def login_student(base_url: str) -> str:
    response = request_json(
        base_url,
        "/api/v1/auth/login",
        method="POST",
        payload={"email": "student1@demo.edu", "password": "Practice123!", "organization_slug": "demo-university"},
    )
    return str(response["access_token"])


def attach_uploaded_image(base_url: str, token: str) -> tuple[str, str]:
    reports = request_json(base_url, "/api/v1/reports?limit=1", token=token)
    report_id = str(reports[0]["id"])
    uploaded = upload_png(base_url, token)
    file_id = str(uploaded["id"])
    document_response = request_json(base_url, f"/api/v1/reports/{report_id}/document", token=token)
    document = document_response["document"]
    section = next(item for item in document["sections"] if item["editable"])
    blocks = list(section["blocks"])
    blocks.append(
        {
            "type": "image",
            "id": "img_backup_restore_verification",
            "file_id": file_id,
            "width_mm": 15,
            "alignment": "center",
            "caption": "Backup restore verification image",
        }
    )
    request_json(
        base_url,
        f"/api/v1/reports/{report_id}/document",
        method="PATCH",
        payload={"expected_revision": document_response["revision"], "sections": {section["id"]: blocks}},
        token=token,
    )
    return report_id, file_id


def verify_restored_document(base_url: str, report_id: str, file_id: str) -> None:
    token = login_student(base_url)
    image = request_bytes(base_url, f"/api/v1/files/{file_id}", token=token)
    if image != PNG_BYTES:
        raise AssertionError("Restored file bytes do not match the uploaded PNG")
    document_response = request_json(base_url, f"/api/v1/reports/{report_id}/document", token=token)
    image_ids = {
        block.get("file_id")
        for section in document_response["document"]["sections"]
        for block in section["blocks"]
        if block.get("type") == "image"
    }
    if file_id not in image_ids:
        raise AssertionError("Restored report document no longer references the uploaded image")
    export = request_bytes(base_url, f"/api/v1/reports/{report_id}/export/docx", token=token)
    with zipfile.ZipFile(io.BytesIO(export)) as document:
        if not any(name.startswith("word/media/") for name in document.namelist()):
            raise AssertionError("DOCX export from restored environment does not contain the image")


def run_backup(bundle_root: Path, source_env: dict[str, str]) -> None:
    if platform.system() == "Windows":
        run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ROOT / "scripts" / "backup-postgres.ps1"),
                "-OutputDirectory",
                str(bundle_root),
                "-ComposeFile",
                str(COMPOSE_FILE),
                "-ProjectName",
                SOURCE_PROJECT,
            ],
            env=source_env,
        )
    else:
        run(["sh", str(ROOT / "scripts" / "backup-postgres.sh"), str(bundle_root)], env=source_env)


def run_restore(bundle: Path, restore_env: dict[str, str]) -> None:
    if platform.system() == "Windows":
        run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ROOT / "scripts" / "restore-practiceflow.ps1"),
                "-BackupDirectory",
                str(bundle),
                "-ConfirmEmptyTarget",
                "-ComposeFile",
                str(COMPOSE_FILE),
                "-ProjectName",
                RESTORE_PROJECT,
            ],
            env=restore_env,
        )
    else:
        run(
            ["sh", str(ROOT / "scripts" / "restore-practiceflow.sh"), str(bundle), "--confirm-empty-target"],
            env=restore_env,
        )


def verify_manifest(bundle: Path) -> None:
    manifest_path = bundle / "manifest.json"
    manifest_checksum_parts = (bundle / "manifest.sha256").read_text(encoding="utf-8").strip().split()
    if len(manifest_checksum_parts) != 2 or manifest_checksum_parts[1] != "manifest.json":
        raise AssertionError("Backup manifest checksum file is invalid")
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != manifest_checksum_parts[0].lower():
        raise AssertionError("Backup manifest checksum does not match manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["format_version"] != 1 or not manifest.get("created_at_utc"):
        raise AssertionError("Backup manifest is missing version or timestamp")
    expected = {entry["name"]: entry for entry in manifest["artifacts"]}
    for name in ("database.dump", "backend-storage.tar.gz"):
        artifact = expected.get(name)
        path = bundle / name
        if not artifact or hashlib.sha256(path.read_bytes()).hexdigest() != artifact["sha256"]:
            raise AssertionError(f"Invalid manifest checksum for {name}")


def main() -> int:
    source_env = {**os.environ, "BACKUP_VERIFY_BACKEND_PORT": SOURCE_PORT, "SEED_ON_START": "true"}
    restore_env = {**os.environ, "BACKUP_VERIFY_BACKEND_PORT": RESTORE_PORT, "SEED_ON_START": "false"}
    bundle_root = Path(tempfile.mkdtemp(prefix="practiceflow-backup-verify-"))
    try:
        run(compose(SOURCE_PROJECT, "up", "-d", "--build", "--wait" , env=source_env), env=source_env)
        source_url = f"http://127.0.0.1:{SOURCE_PORT}"
        wait_for_api(source_url)
        source_token = login_student(source_url)
        report_id, file_id = attach_uploaded_image(source_url, source_token)
        run_backup(bundle_root, source_env)
        bundles = [path for path in bundle_root.iterdir() if path.is_dir() and path.name.startswith("practiceflow-backup-")]
        if len(bundles) != 1:
            raise AssertionError("Expected exactly one completed backup bundle")
        bundle = bundles[0]
        verify_manifest(bundle)

        run(compose(RESTORE_PROJECT, "build", "backend", env=restore_env), env=restore_env)
        run(compose(RESTORE_PROJECT, "up", "-d", "--wait", "postgres", env=restore_env), env=restore_env)
        run_restore(bundle, restore_env)
        run(compose(RESTORE_PROJECT, "up", "-d", "--wait", "backend", env=restore_env), env=restore_env)
        restore_url = f"http://127.0.0.1:{RESTORE_PORT}"
        wait_for_api(restore_url)
        verify_restored_document(restore_url, report_id, file_id)
        print("Backup/restore verification passed: uploaded image, report reference and DOCX export survived restore.")
        return 0
    finally:
        for project, env in ((SOURCE_PROJECT, source_env), (RESTORE_PROJECT, restore_env)):
            try:
                run(compose(project, "down", "--volumes", "--remove-orphans", env=env), env=env)
            except subprocess.CalledProcessError:
                print(f"WARNING: could not clean temporary project {project}", file=sys.stderr)
        shutil.rmtree(bundle_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
