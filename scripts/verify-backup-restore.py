#!/usr/bin/env python3
"""Disposable end-to-end verification for the local-volume backup bundle.

It provisions independent source and restore Compose projects, uploads a PDF
teaching material through the real API, runs the platform backup/restore
scripts, and verifies the restored discipline topic and material bytes.
"""

from __future__ import annotations

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
PDF_BYTES = (
    b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"
)
DOCX_MIME = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


def synthetic_docx_bytes(body: str = "PracticeFlow backup verification") -> bytes:
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
        'officeDocument" Target="word/document.xml"/></Relationships>'
    )
    document_xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{body}</w:t></w:r></w:p></w:body></w:document>"
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in (
            ("[Content_Types].xml", content_types),
            ("_rels/.rels", rels),
            ("word/document.xml", document_xml),
        ):
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, value)
    return output.getvalue()


DOCX_BYTES = synthetic_docx_bytes()


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
        raise subprocess.CalledProcessError(
            completed.returncode, command, completed.stdout
        )
    return completed.stdout or ""


def compose(project: str, *args: str, env: dict[str, str]) -> list[str]:
    return [
        "docker",
        "compose",
        "--project-name",
        project,
        "-f",
        str(COMPOSE_FILE),
        *args,
    ]


def request_json(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: object | None = None,
    token: str | None = None,
) -> object:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"{base_url}{path}", data=data, headers=headers, method=method
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def request_bytes(base_url: str, path: str, *, token: str) -> bytes:
    request = urllib.request.Request(
        f"{base_url}{path}", headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def wait_for_api(base_url: str) -> None:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(
                f"{base_url}/health/ready", timeout=3
            ) as response:
                if response.status == 200:
                    return
        except urllib.error.URLError:
            pass
        time.sleep(1)
    raise RuntimeError(f"Timed out waiting for {base_url}")


def login_teacher(base_url: str) -> str:
    response = request_json(
        base_url,
        "/api/v1/auth/login",
        method="POST",
        payload={
            "email": "teacher@demo.edu",
            "password": "Practice123!",
            "organization_slug": "demo-university",
        },
    )
    return str(response["access_token"])


def upload_teaching_material(base_url: str, token: str) -> tuple[str, str]:
    discipline = request_json(
        base_url,
        "/api/v1/disciplines",
        method="POST",
        payload={
            "name": f"Backup verification {uuid.uuid4().hex[:8]}",
            "description": "Synthetic backup verification discipline",
            "academic_year": "2026-2027",
            "group_ids": [],
        },
        token=token,
    )
    discipline_id = str(discipline["id"])
    topic = request_json(
        base_url,
        f"/api/v1/disciplines/{discipline_id}/topics",
        method="POST",
        payload={
            "title": "Backup verification topic",
            "description": "Topic for backup drill",
            "learning_goal": "Verify teaching material persistence",
        },
        token=token,
    )
    topic_id = str(topic["id"])
    boundary = f"----PracticeFlowBackup{uuid.uuid4().hex}"
    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="file"; filename="backup-verification.pdf"\r\n',
            b"Content-Type: application/pdf\r\n\r\n",
            PDF_BYTES,
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )
    request = urllib.request.Request(
        f"{base_url}/api/v1/topics/{topic_id}/materials",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Idempotency-Key": uuid.uuid4().hex,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        material = json.loads(response.read().decode("utf-8"))
    return topic_id, str(material["id"])


def verify_restored_material(
    base_url: str, topic_id: str, material_id: str
) -> None:
    token = login_teacher(base_url)
    materials = request_json(
        base_url, f"/api/v1/topics/{topic_id}/materials", token=token
    )
    if not any(str(item["id"]) == material_id for item in materials):
        raise AssertionError("Restored topic does not list the uploaded material")
    content = request_bytes(
        base_url, f"/api/v1/materials/{material_id}/download", token=token
    )
    if content != PDF_BYTES:
        raise AssertionError(
            "Restored teaching material bytes do not match the uploaded PDF"
        )


def ensure_published_profile_version(base_url: str, token: str) -> str:
    profiles = request_json(base_url, "/api/v1/check-profiles", token=token)
    for profile in profiles:
        for version in profile.get("versions", []):
            if version.get("state") == "PUBLISHED":
                return str(version["id"])
    created = request_json(
        base_url,
        "/api/v1/check-profiles",
        method="POST",
        payload={"name": f"Backup check profile {uuid.uuid4().hex[:8]}"},
        token=token,
    )
    profile_id = str(created["id"])
    version = request_json(
        base_url,
        f"/api/v1/check-profiles/{profile_id}/versions",
        method="POST",
        payload={},
        token=token,
    )
    version_id = str(version["id"])
    request_json(
        base_url,
        f"/api/v1/check-profiles/{profile_id}/versions/{version_id}/rules",
        method="PUT",
        payload={
            "rules": [
                {
                    "rule_type": "PAGE_FORMAT_MARGINS",
                    "category": "formatting",
                    "severity": "ERROR",
                    "enabled": True,
                    "sort_order": 0,
                    "config_schema_version": 1,
                    "config": {
                        "page_size": "A4",
                        "orientation": "PORTRAIT",
                        "margins": {
                            "top_mm": 20.0,
                            "right_mm": 15.0,
                            "bottom_mm": 20.0,
                            "left_mm": 30.0,
                        },
                        "width_mm": None,
                        "height_mm": None,
                    },
                }
            ]
        },
        token=token,
    )
    published = request_json(
        base_url,
        f"/api/v1/check-profiles/{profile_id}/versions/{version_id}/publish",
        method="POST",
        token=token,
    )
    return str(published["id"])


def upload_teacher_docx_submission(
    base_url: str, token: str, *, profile_version_id: str | None = None
) -> str:
    version_id = profile_version_id or ensure_published_profile_version(
        base_url, token
    )
    boundary = f"----PracticeFlowDocx{uuid.uuid4().hex}"
    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="profile_version_id"\r\n\r\n',
            version_id.encode("utf-8"),
            f"\r\n--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="file"; filename="backup-check.docx"\r\n',
            f"Content-Type: {DOCX_MIME}\r\n\r\n".encode(),
            DOCX_BYTES,
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )
    request = urllib.request.Request(
        f"{base_url}/api/v1/document-checks/teacher/submissions",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Idempotency-Key": uuid.uuid4().hex,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        submission = json.loads(response.read().decode("utf-8"))
    return str(submission["id"])


def wait_for_teacher_submission(
    base_url: str, token: str, submission_id: str
) -> dict[str, object]:
    deadline = time.monotonic() + 120
    while True:
        submission = request_json(
            base_url,
            f"/api/v1/document-checks/teacher/submissions/{submission_id}",
            token=token,
        )
        job = submission["job"]
        if job["status"] == "COMPLETED":
            return submission
        assert job["status"] in {"QUEUED", "PROCESSING"}, (
            "Document check job failed"
        )
        assert time.monotonic() < deadline, "Document check job timed out"
        time.sleep(1)


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
        run(
            ["sh", str(ROOT / "scripts" / "backup-postgres.sh"), str(bundle_root)],
            env=source_env,
        )


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
            [
                "sh",
                str(ROOT / "scripts" / "restore-practiceflow.sh"),
                str(bundle),
                "--confirm-empty-target",
            ],
            env=restore_env,
        )


def verify_manifest(bundle: Path) -> None:
    manifest_path = bundle / "manifest.json"
    manifest_checksum_parts = (
        (bundle / "manifest.sha256").read_text(encoding="utf-8").strip().split()
    )
    if (
        len(manifest_checksum_parts) != 2
        or manifest_checksum_parts[1] != "manifest.json"
    ):
        raise AssertionError("Backup manifest checksum file is invalid")
    if (
        hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        != manifest_checksum_parts[0].lower()
    ):
        raise AssertionError(
            "Backup manifest checksum does not match manifest.json"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["format_version"] != 1 or not manifest.get("created_at_utc"):
        raise AssertionError("Backup manifest is missing version or timestamp")
    expected = {entry["name"]: entry for entry in manifest["artifacts"]}
    for name in ("database.dump", "backend-storage.tar.gz"):
        artifact = expected.get(name)
        path = bundle / name
        if (
            not artifact
            or hashlib.sha256(path.read_bytes()).hexdigest()
            != artifact["sha256"]
        ):
            raise AssertionError(f"Invalid manifest checksum for {name}")


def main() -> int:
    source_env = {
        **os.environ,
        "BACKUP_VERIFY_BACKEND_PORT": SOURCE_PORT,
        "SEED_ON_START": "true",
    }
    restore_env = {
        **os.environ,
        "BACKUP_VERIFY_BACKEND_PORT": RESTORE_PORT,
        "SEED_ON_START": "false",
    }
    bundle_root = Path(tempfile.mkdtemp(prefix="practiceflow-backup-verify-"))
    try:
        run(
            compose(
                SOURCE_PROJECT, "up", "-d", "--build", "--wait", env=source_env
            ),
            env=source_env,
        )
        source_url = f"http://127.0.0.1:{SOURCE_PORT}"
        wait_for_api(source_url)
        source_token = login_teacher(source_url)
        topic_id, material_id = upload_teaching_material(source_url, source_token)
        run_backup(bundle_root, source_env)
        bundles = [
            path
            for path in bundle_root.iterdir()
            if path.is_dir() and path.name.startswith("practiceflow-backup-")
        ]
        if len(bundles) != 1:
            raise AssertionError("Expected exactly one completed backup bundle")
        bundle = bundles[0]
        verify_manifest(bundle)

        run(
            compose(RESTORE_PROJECT, "build", "backend", env=restore_env),
            env=restore_env,
        )
        run(
            compose(
                RESTORE_PROJECT,
                "up",
                "-d",
                "--wait",
                "postgres",
                env=restore_env,
            ),
            env=restore_env,
        )
        run_restore(bundle, restore_env)
        run(
            compose(
                RESTORE_PROJECT, "up", "-d", "--wait", "backend", env=restore_env
            ),
            env=restore_env,
        )
        restore_url = f"http://127.0.0.1:{RESTORE_PORT}"
        wait_for_api(restore_url)
        verify_restored_material(restore_url, topic_id, material_id)
        print(
            "Backup/restore verification passed: uploaded teaching material and topic reference survived restore."
        )
        return 0
    finally:
        for project, env in (
            (SOURCE_PROJECT, source_env),
            (RESTORE_PROJECT, restore_env),
        ):
            try:
                run(
                    compose(
                        project,
                        "down",
                        "--volumes",
                        "--remove-orphans",
                        env=env,
                    ),
                    env=env,
                )
            except subprocess.CalledProcessError:
                print(
                    f"WARNING: could not clean temporary project {project}",
                    file=sys.stderr,
                )
        shutil.rmtree(bundle_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
