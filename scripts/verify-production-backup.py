#!/usr/bin/env python3
"""Real, synthetic-only restore drill; run inside testing/backup/Dockerfile.

The runner needs the Docker socket and this checkout mounted at /workspace.
No host ports, real accounts, production environment files or documents used.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from production_backup import ENGINE, Backup, run

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.production-backup.verify.yml"
spec = importlib.util.spec_from_file_location(
    "local_drill", ROOT / "scripts/verify-backup-restore.py"
)
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


def cli(config, command, *args, success=True):
    result = subprocess.run(
        [
            "python",
            str(ROOT / "scripts/production_backup.py"),
            "--config",
            str(config),
            command,
            *args,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if success:
        if result.returncode:
            raise RuntimeError(result.stderr.strip())
        return json.loads(result.stdout)
    assert result.returncode != 0, "Unsafe operation unexpectedly succeeded"
    assert "local_only" not in result.stderr, "Credential appeared in failure log"


def verify_application(base_url, topic_id, material_id):
    """Exercise teaching material readback and the real document-check worker."""
    token = api.login_teacher(base_url)
    api.verify_restored_material(base_url, topic_id, material_id)
    submission_id = api.upload_teacher_docx_submission(base_url, token)
    api.wait_for_teacher_submission(base_url, token, submission_id)
    content = api.request_bytes(
        base_url,
        f"/api/v1/document-checks/teacher/submissions/{submission_id}/original",
        token=token,
    )
    assert content == api.DOCX_BYTES, "Uploaded DOCX bytes did not match original"
    return submission_id


def main():
    started = time.monotonic()
    suffix = uuid.uuid4().hex[:12]
    source, target = (
        f"pf-backup-test-{suffix}-{part}" for part in ("source", "restore")
    )
    runner = os.environ["HOSTNAME"]
    os.environ.update(
        PF_SOURCE_ACCESS_KEY="practiceflow_e2e_minio",
        PF_SOURCE_SECRET_KEY="practiceflow_e2e_minio_local_only",
        PF_VAULT_ACCESS_KEY="practiceflow_backup_vault",
        PF_VAULT_SECRET_KEY="practiceflow_backup_vault_local_only",
    )
    app_image = f"pf-backup-test-{suffix}-app"

    def compose(project, *args):
        env = {
            **os.environ,
            "BACKUP_TEST_PROJECT": project,
            "BACKUP_TEST_APP_IMAGE": app_image,
        }
        if args[0] == "build":
            # Build inputs are synthetic/source-only. Streaming build progress
            # avoids an opaque long wait; runtime output remains suppressed.
            subprocess.run(
                [
                    "docker",
                    "compose",
                    "--project-name",
                    project,
                    "-f",
                    str(COMPOSE),
                    *args,
                ],
                env=env,
                check=True,
            )
            return b""
        try:
            return run(
                [
                    "docker",
                    "compose",
                    "--project-name",
                    project,
                    "-f",
                    str(COMPOSE),
                    *args,
                ],
                env=env,
            )
        except RuntimeError:
            # A disposable fixture may report state and probe exit codes, never
            # container environment, raw healthcheck output or application logs.
            print(json.dumps({"fixture_operation_failed": args[0]}), flush=True)
            ids = (
                run(
                    [
                        "docker",
                        "ps",
                        "-aq",
                        "--filter",
                        f"label=com.docker.compose.project={project}",
                    ]
                )
                .decode()
                .split()
            )
            for container in (
                json.loads(run(["docker", "inspect", *ids])) if ids else []
            ):
                state = container["State"]
                health = state.get("Health", {})
                print(
                    json.dumps(
                        {
                            "service": container["Config"]["Labels"][
                                "com.docker.compose.service"
                            ],
                            "status": state["Status"],
                            "exit_code": state["ExitCode"],
                            "oom_killed": state["OOMKilled"],
                            "health": health.get("Status"),
                            "probe_exit_codes": [
                                probe["ExitCode"] for probe in health.get("Log", [])
                            ],
                        }
                    ),
                    flush=True,
                )
            raise

    # Authorize cleanup only for UUID namespaces proven unused before creation.
    for project in (source, target):
        assert not run(
            [
                "docker",
                "ps",
                "-aq",
                "--filter",
                f"label=com.docker.compose.project={project}",
            ]
        ).strip()
    os.umask(0o077)
    with tempfile.TemporaryDirectory(prefix="pf-drill-") as temporary:
        temporary = Path(temporary)
        try:
            print("Building disposable source/restore images", flush=True)
            compose(source, "build", "backend", "minio", "minio-init", "vault")
            compose(
                source,
                "up",
                "-d",
                "--wait",
                "postgres",
                "redis",
                "minio",
                "vault",
            )
            compose(source, "run", "--rm", "--no-deps", "minio-init")
            run(["docker", "network", "connect", f"{source}_default", runner])
            compose(
                source,
                "run",
                "--rm",
                "--no-deps",
                "--entrypoint",
                "sh",
                "backend",
                "-ec",
                "alembic upgrade head && python e2e_seed.py",
            )
            compose(
                source,
                "up",
                "-d",
                "--wait",
                "backend",
                "document-check-worker",
            )
            source_url = f"http://{source}-backend-1:8000"
            api.wait_for_api(source_url)
            topic_id, material_id = api.upload_teaching_material(
                source_url, api.login_teacher(source_url)
            )
            source_submission_id = verify_application(
                source_url, topic_id, material_id
            )
            password = temporary / "password"
            password.write_text(uuid.uuid4().hex + uuid.uuid4().hex)
            config = {
                "installation": f"drill-{suffix}",
                "project": source,
                "test_mode": True,
                "compose_files": [str(COMPOSE)],
                "state_directory": str(temporary / "source-state"),
                "storage": {
                    "endpoint": f"http://{source}-minio-1:9000",
                    "bucket": "practiceflow-e2e",
                    "region": "us-east-1",
                    "access_key_env": "PF_SOURCE_ACCESS_KEY",
                    "secret_key_env": "PF_SOURCE_SECRET_KEY",
                },
                "repository": f"s3:http://{source}-vault-1:9000/vault/dr",
                "password_file": str(password),
                "vault_region": "us-east-1",
                "vault_access_key_env": "PF_VAULT_ACCESS_KEY",
                "vault_secret_key_env": "PF_VAULT_SECRET_KEY",
                "retention_days": 1,
                "keep_last": 1,
            }
            os.environ.update(
                BACKUP_TEST_PROJECT=source, BACKUP_TEST_APP_IMAGE=app_image
            )
            instance = Backup(config)
            import boto3

            vault = boto3.client(
                "s3",
                endpoint_url=f"http://{source}-vault-1:9000",
                aws_access_key_id=os.environ["PF_VAULT_ACCESS_KEY"],
                aws_secret_access_key=os.environ["PF_VAULT_SECRET_KEY"],
                region_name="us-east-1",
            )
            vault.create_bucket(Bucket="vault")
            instance.restic("init")
            config["repository_id"] = json.loads(instance.restic("cat", "config"))["id"]
            source_config = temporary / "source.json"
            source_config.write_text(json.dumps(config))
            # Include unreferenced bytes: a DB-reference-only backup is incomplete.
            s3, bucket = instance.storage()
            s3.put_object(
                Bucket=bucket,
                Key="unreferenced-fixture",
                Body=b"synthetic orphan bytes",
            )
            print(
                "Backing up live API + document-check worker; verifying remote readback",
                flush=True,
            )
            backup = cli(source_config, "backup")
            assert len(instance.writers()) == 2, "Original API/worker were not resumed"
            assert backup["objects"] >= 3
            # A mid-capture completeness failure must resume the worker and API,
            # and must not publish or expire any snapshot.
            material_key = instance.sql(
                "SELECT storage_key FROM teaching_materials ORDER BY storage_key LIMIT 1"
            )
            material_obj = s3.get_object(Bucket=bucket, Key=material_key)
            material_bytes = material_obj["Body"].read()
            s3.delete_object(Bucket=bucket, Key=material_key)
            cli(source_config, "backup", success=False)
            assert len(instance.writers()) == 2
            assert len(instance.owned_snapshots()) == 1
            s3.put_object(
                Bucket=bucket,
                Key=material_key,
                Body=material_bytes,
                ContentType=material_obj["ContentType"],
            )
            # The source project/bucket must never be a restore destination.
            cli(
                source_config,
                "restore",
                "--snapshot",
                backup["snapshot"],
                "--confirm-empty-target",
                success=False,
            )

            # A failed repository preflight must leave every writer running.
            bad = {**config, "repository_id": "0" * 64}
            bad_path = temporary / "bad.json"
            bad_path.write_text(json.dumps(bad))
            cli(bad_path, "backup", success=False)
            assert len(instance.writers()) == 2

            print(
                "Restoring into a new empty PostgreSQL + independent private bucket",
                flush=True,
            )
            recovery_started = time.monotonic()
            compose(target, "up", "-d", "--wait", "postgres", "redis", "minio")
            compose(target, "run", "--rm", "--no-deps", "minio-init")
            run(["docker", "network", "connect", f"{target}_default", runner])
            restored_config = {
                **config,
                "project": target,
                "state_directory": str(temporary / "target-state"),
                "storage": {
                    **config["storage"],
                    "endpoint": f"http://{target}-minio-1:9000",
                },
            }
            target_config = temporary / "target.json"
            target_config.write_text(json.dumps(restored_config))
            os.environ["BACKUP_TEST_PROJECT"] = target
            restore = cli(
                target_config,
                "restore",
                "--snapshot",
                backup["snapshot"],
                "--confirm-empty-target",
            )
            assert restore["objects"] == backup["objects"]
            # Refuse nonempty DB/bucket, including retries after a partial restore.
            cli(
                target_config,
                "restore",
                "--snapshot",
                backup["snapshot"],
                "--confirm-empty-target",
                success=False,
            )
            compose(
                target,
                "up",
                "-d",
                "--wait",
                "backend",
                "document-check-worker",
            )
            verify_started = time.monotonic()
            target_url = f"http://{target}-backend-1:8000"
            api.wait_for_api(target_url)
            restored_docx = api.request_bytes(
                target_url,
                f"/api/v1/document-checks/teacher/submissions/{source_submission_id}/original",
                token=api.login_teacher(target_url),
            )
            assert restored_docx == api.DOCX_BYTES, (
                "Previously uploaded teacher DOCX submission did not survive restore"
            )
            verify_application(target_url, topic_id, material_id)
            api_seconds = round(time.monotonic() - verify_started, 3)
            recovery_seconds = round(time.monotonic() - recovery_started, 3)
            recovered_s3, recovered_bucket = Backup(restored_config).storage()
            assert (
                recovered_s3.get_object(
                    Bucket=recovered_bucket, Key="unreferenced-fixture"
                )["Body"].read()
                == b"synthetic orphan bytes"
            )

            # Retention must preserve foreign snapshots even in the same repository.
            unrelated = temporary / "unrelated"
            unrelated.write_text("synthetic unrelated backup")
            instance.restic(
                "backup",
                "--host",
                config["installation"],
                "--tag",
                "unrelated",
                str(unrelated),
            )
            before = json.loads(instance.restic("snapshots", "--json"))
            instance.restic(
                "backup",
                "--host",
                config["installation"],
                "--tag",
                ENGINE,
                "--tag",
                config["installation"],
                "--time",
                "2001-01-01 00:00:00",
                str(unrelated),
            )
            assert len(instance.owned_snapshots()) == 2
            instance.retain(backup["snapshot"])
            after = json.loads(instance.restic("snapshots", "--json"))
            assert {s["id"] for s in before} == {s["id"] for s in after}
            from urllib.error import HTTPError
            from urllib.request import urlopen

            try:
                urlopen(f"http://{target}-minio-1:9000/{bucket}/unreferenced-fixture")
                raise AssertionError("Anonymous object access succeeded")
            except HTTPError as error:
                assert error.code == 403
            instance.restic("check", "--read-data")
            print(
                json.dumps(
                    {
                        "status": "PASS",
                        "backup": backup,
                        "restore": restore,
                        "application_verification_seconds": api_seconds,
                        "empty_target_through_application_seconds": recovery_seconds,
                        "drill_total_seconds": round(time.monotonic() - started, 3),
                        "checks": [
                            "full remote readback",
                            "API teaching material bytes",
                            "teacher DOCX submission original",
                            "document-check worker job completion",
                            "unreferenced object",
                            "writers resumed",
                            "capture failure resumes writers",
                            "source restore rejected",
                            "nonempty restore rejected",
                            "expired owned snapshot deleted",
                            "foreign snapshot preserved",
                            "anonymous object denied",
                            "repository full data check",
                        ],
                    }
                ),
                flush=True,
            )
            return 0
        finally:
            failed = False
            for project in (source, target):
                try:
                    run(
                        [
                            "docker",
                            "network",
                            "disconnect",
                            "-f",
                            f"{project}_default",
                            runner,
                        ]
                    )
                except RuntimeError:
                    pass
                try:
                    compose(project, "down", "--volumes", "--remove-orphans")
                except RuntimeError:
                    failed = True
            if failed:
                raise RuntimeError("Could not remove a disposable drill project")


if __name__ == "__main__":
    raise SystemExit(main())
