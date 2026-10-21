#!/usr/bin/env python3
"""Coordinated PostgreSQL/private-S3 backups in an encrypted restic repository.

Only fixed status messages reach logs. Provider/Compose/restic output can contain
credentials or object keys and is deliberately never forwarded on failure.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

import boto3
from botocore.config import Config

ENGINE = "practiceflow-postgres-s3-v2"
SNAPSHOT_ROOT = "/bundle"
SAFE_SERVICES = {"postgres", "redis", "frontend", "caddy"}
REFERENCES_SQL = """
SELECT coalesce(json_agg(r ORDER BY key, size_bytes NULLS FIRST), '[]') FROM (
 SELECT storage_key AS key, size_bytes, NULL::text AS sha256 FROM files
 UNION ALL SELECT storage_key, size_bytes, NULL FROM export_jobs
   WHERE status = 'succeeded' AND storage_key IS NOT NULL
 UNION ALL SELECT storage_key, NULL, NULL FROM group_review_reports
   WHERE generated_at IS NOT NULL AND storage_key IS NOT NULL
 UNION ALL SELECT storage_key, size_bytes, sha256 FROM teaching_materials
   WHERE storage_deleted_at IS NULL
 UNION ALL SELECT storage_key, size_bytes, sha256 FROM student_document_submissions
 UNION ALL SELECT s.storage_key, s.size_bytes, s.sha256 FROM teacher_document_submissions s
   LEFT JOIN teacher_document_lifecycle l ON l.submission_id=s.id AND l.organization_id=s.organization_id
   WHERE l.original_deleted_at IS NULL
) r
"""
EMPTY_SQL = """SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname NOT IN ('pg_catalog','information_schema')
AND n.nspname NOT LIKE 'pg_toast%' AND c.relkind IN ('r','p','v','m','S','f')"""


class BackupError(RuntimeError):
    """An operator-safe, fixed diagnostic without external values."""


def require(condition, message):
    if not condition:
        raise BackupError(message)


def run(args, *, env=None, cwd=None, stdin=None, stdout=None):
    result = subprocess.run(
        args,
        env=env,
        cwd=cwd,
        stdin=stdin,
        stdout=stdout or subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10800,
        check=False,
    )
    operation = "external command"
    if args[0] == "restic":
        commands = {
            "cat",
            "backup",
            "restore",
            "check",
            "snapshots",
            "forget",
            "prune",
            "init",
        }
        operation = "restic " + next(
            (arg for arg in args[1:] if arg in commands), "operation"
        )
    require(result.returncode == 0, f"{operation} failed; sensitive output suppressed")
    return result.stdout or b""


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def artifact(path):
    return {
        "name": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": digest(path),
    }


def fingerprint(storage):
    return hashlib.sha256(
        (storage["endpoint"].rstrip("/") + "/" + storage["bucket"]).encode()
    ).hexdigest()


def inventory(client, bucket):
    return {
        obj["Key"]: {
            "size": obj["Size"],
            "etag": obj["ETag"],
            "modified": obj["LastModified"].isoformat(),
        }
        for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket)
        for obj in page.get("Contents", [])
    }


def copy_body(body, path):
    try:
        with path.open("wb") as stream:
            while chunk := body.read(1024 * 1024):
                stream.write(chunk)
    finally:
        body.close()


def validate_bundle(bundle, installation):
    manifest_path = bundle / "manifest.json"
    require(
        digest(manifest_path) == (bundle / "manifest.sha256").read_text().strip(),
        "Manifest checksum mismatch",
    )
    manifest = json.loads(manifest_path.read_text())
    require(
        manifest["engine"] == ENGINE and manifest["installation"] == installation,
        "Wrong bundle format or installation",
    )
    require(
        manifest["object_count"] == len(manifest["objects"]),
        "Incomplete object manifest",
    )
    names, keys = {"manifest.json", "manifest.sha256"}, set()
    for item in [manifest["database"], *manifest["objects"]]:
        name = item["name"]
        require(
            name == "database.dump" or re.fullmatch(r"object-[0-9]{8}", name),
            "Invalid artifact name",
        )
        require(name not in names, "Duplicate artifact")
        names.add(name)
        path = bundle / name
        require(
            path.is_file()
            and not path.is_symlink()
            and artifact(path)
            == {k: item[k] for k in ("name", "size_bytes", "sha256")},
            "Artifact checksum or size mismatch",
        )
        if "key" in item:
            require(item["key"] not in keys, "Duplicate object key")
            keys.add(item["key"])
    require({p.name for p in bundle.iterdir()} == names, "Unexpected bundle contents")
    by_key = {obj["key"]: obj for obj in manifest["objects"]}
    for ref in manifest["references"]:
        item = by_key.get(ref["key"])
        require(
            item is not None
            and (ref["size_bytes"] is None or ref["size_bytes"] == item["size_bytes"]),
            "Database reference has no complete object",
        )
        require(
            not ref.get("sha256") or ref["sha256"] == item["sha256"],
            "Database object digest mismatch",
        )
    return manifest


class Backup:
    def __init__(self, config):
        self.c = config
        self.project = config["project"]
        self.test = config.get("test_mode", False)
        require(
            re.fullmatch(r"[a-z0-9][a-z0-9_-]+", self.project),
            "Invalid explicit Compose project",
        )
        require(
            not self.test or self.project.startswith("pf-backup-test-"),
            "Test mode requires a disposable project",
        )
        require(
            re.fullmatch(r"[a-zA-Z0-9_-]{8,64}", config["installation"]),
            "Invalid installation ID",
        )
        require(
            int(config["retention_days"]) >= 1 and int(config["keep_last"]) >= 1,
            "Unsafe retention",
        )
        self.state = Path(config["state_directory"]).resolve()
        self.state.mkdir(mode=0o700, parents=True, exist_ok=True)
        require(
            self.state.stat().st_mode & 0o077 == 0,
            "State directory must have mode 0700",
        )
        self.journal = self.state / "resume.json"
        self.compose = ["docker", "compose", "--project-name", self.project]
        if config.get("env_file"):
            self.compose += ["--env-file", config["env_file"]]
        for file in config["compose_files"]:
            self.compose += ["-f", file]
        self.safe = SAFE_SERVICES | ({"minio", "vault"} if self.test else set())

    def containers(self):
        ids = (
            run(
                [
                    "docker",
                    "ps",
                    "-aq",
                    "--filter",
                    f"label=com.docker.compose.project={self.project}",
                ]
            )
            .decode()
            .split()
        )
        return json.loads(run(["docker", "inspect", *ids])) if ids else []

    @staticmethod
    def service(container):
        return container["Config"]["Labels"]["com.docker.compose.service"]

    def writers(self):
        return [
            c
            for c in self.containers()
            if self.service(c) not in self.safe and c["State"]["Running"]
        ]

    def sql(self, sql):
        return (
            run(
                [
                    *self.compose,
                    "exec",
                    "-T",
                    "postgres",
                    "sh",
                    "-ec",
                    'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "$1"',
                    "sh",
                    sql,
                ]
            )
            .decode()
            .strip()
        )

    def storage(self):
        s = self.c["storage"]
        endpoint = urlsplit(s["endpoint"])
        require(endpoint.scheme == "https" or self.test, "S3 requires verified HTTPS")
        require(
            not endpoint.username and not endpoint.password,
            "Credentials must not appear in endpoint",
        )
        client = boto3.client(
            "s3",
            endpoint_url=s["endpoint"],
            region_name=s["region"],
            aws_access_key_id=os.environ[s["access_key_env"]],
            aws_secret_access_key=os.environ[s["secret_key_env"]],
            verify=True,
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=15,
                read_timeout=120,
                s3={"addressing_style": s.get("addressing_style", "path")},
            ),
        )
        client.head_bucket(Bucket=s["bucket"])
        return client, s["bucket"]

    def restic(self, *args, cwd=None):
        c = self.c
        repo = c["repository"]
        if not self.test:
            require(
                repo.startswith("s3:https://"),
                "Backup repository must use off-site HTTPS S3",
            )
            url = urlsplit(repo[3:])
            source = urlsplit(c["storage"]["endpoint"])
            require(
                url.hostname != source.hostname,
                "Vault must use an independent storage endpoint",
            )
            require(
                not url.username and not url.password and not url.query,
                "Invalid vault URL",
            )
            require(
                c.get("offsite_private_confirmed") is True,
                "Operator must verify independent host/account and private bucket policy",
            )
        env = {
            k: v
            for k, v in os.environ.items()
            if k in {"PATH", "HOME", "TMPDIR", "SSL_CERT_FILE", "SSL_CERT_DIR"}
        }
        env.update(
            RESTIC_REPOSITORY=repo,
            RESTIC_PASSWORD_FILE=c["password_file"],
            AWS_ACCESS_KEY_ID=os.environ[c["vault_access_key_env"]],
            AWS_SECRET_ACCESS_KEY=os.environ[c["vault_secret_key_env"]],
            AWS_DEFAULT_REGION=c["vault_region"],
        )
        return run(["restic", "--no-cache", *args], env=env, cwd=cwd)

    def check_repository(self):
        password = Path(self.c["password_file"])
        require(
            password.is_file() and password.stat().st_mode & 0o077 == 0,
            "Repository password file must have mode 0600",
        )
        config = json.loads(self.restic("cat", "config"))
        require(
            config["id"] == self.c["repository_id"],
            "Unexpected backup repository identity",
        )

    def resume(self):
        if not self.journal.exists():
            return
        journal = json.loads(self.journal.read_text())
        require(journal["project"] == self.project, "Resume journal project mismatch")
        containers = {c["Id"]: c for c in self.containers()}
        for cid in journal["ids"]:
            require(
                cid in containers and self.service(containers[cid]) not in self.safe,
                "Resume container was removed or changed; manual recovery required",
            )
            run(["docker", "start", cid])
        deadline = time.monotonic() + 180
        while True:
            containers = {c["Id"]: c for c in self.containers()}
            if all(
                containers[cid]["State"]["Running"]
                and containers[cid]["State"].get("Health", {}).get("Status", "healthy")
                == "healthy"
                for cid in journal["ids"]
            ):
                break
            require(
                time.monotonic() < deadline,
                "Restart health check failed; resume journal retained",
            )
            time.sleep(2)
        self.journal.unlink()

    @contextlib.contextmanager
    def paused(self):
        require(
            not self.journal.exists(),
            "Unfinished backup: run resume before starting another backup",
        )
        require(
            self.test or self.c.get("external_writers_fenced") is True,
            "Operator must fence external writers, deployments and bucket lifecycle jobs",
        )
        writers = sorted(self.writers(), key=lambda c: self.service(c) != "backend")
        require(
            any(self.service(c) == "backend" for c in writers),
            "Source API must be running",
        )
        pg = next(c for c in self.containers() if self.service(c) == "postgres")
        pg_env = dict(v.split("=", 1) for v in pg["Config"]["Env"])
        for container in writers:
            env = dict(v.split("=", 1) for v in container["Config"]["Env"])
            require(
                env.get("STORAGE_BACKEND") == "s3",
                "Unknown writer; maintenance configuration required",
            )
            db = urlsplit(env["DATABASE_URL"])
            require(
                db.hostname == "postgres" and db.path == "/" + pg_env["POSTGRES_DB"],
                "Writer database differs from Compose PostgreSQL",
            )
            require(
                env["S3_ENDPOINT_URL"].rstrip("/")
                == self.c["storage"]["endpoint"].rstrip("/")
                and env["S3_BUCKET"] == self.c["storage"]["bucket"],
                "Writer S3 target mismatch",
            )
        self.journal.write_text(
            json.dumps({"project": self.project, "ids": [c["Id"] for c in writers]})
        )
        # Persist restart intent before the first stop, including across power loss.
        with self.journal.open("r+") as stream:
            os.fsync(stream.fileno())
        directory_fd = os.open(self.state, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        try:
            for container in writers:
                run(["docker", "stop", "--time", "120", container["Id"]])
            require(not self.writers(), "A writer is still running")
            stopped = {c["Id"]: c for c in self.containers()}
            require(
                all(stopped[c["Id"]]["State"]["ExitCode"] != 137 for c in writers),
                "A writer required SIGKILL; no consistent backup published",
            )
            yield
        finally:
            self.resume()

    def capture(self, bundle):
        client, bucket = self.storage()
        connections_sql = "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND backend_type='client backend'"
        require(
            self.sql(connections_sql) == "0",
            "Other database clients are connected during capture",
        )
        before = inventory(client, bucket)
        refs = json.loads(self.sql(REFERENCES_SQL))
        with (bundle / "database.dump").open("wb") as output:
            run(
                [
                    *self.compose,
                    "exec",
                    "-T",
                    "postgres",
                    "sh",
                    "-ec",
                    'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-acl',
                ],
                stdout=output,
            )
        require((bundle / "database.dump").stat().st_size > 0, "Empty database dump")
        objects = []
        for index, (key, entry) in enumerate(sorted(before.items())):
            response = client.get_object(Bucket=bucket, Key=key, IfMatch=entry["etag"])
            path = bundle / f"object-{index:08d}"
            copy_body(response["Body"], path)
            require(path.stat().st_size == entry["size"], "Incomplete S3 download")
            objects.append(
                {
                    **artifact(path),
                    "key": key,
                    "etag": entry["etag"],
                    "version_id": response.get("VersionId"),
                    "content_type": response.get(
                        "ContentType", "application/octet-stream"
                    ),
                    "metadata": response.get("Metadata", {}),
                }
            )
        require(before == inventory(client, bucket), "S3 changed during capture")
        require(
            self.sql(connections_sql) == "0", "Database client connected during capture"
        )
        require(not self.writers(), "A writer restarted during capture")
        manifest = {
            "engine": ENGINE,
            "installation": self.c["installation"],
            "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "source_project": self.project,
            "source_storage": fingerprint(self.c["storage"]),
            "postgres_version": self.sql("SHOW server_version"),
            "alembic_revision": self.sql(
                "SELECT version_num FROM alembic_version ORDER BY version_num"
            ),
            "application_images": sorted(
                {
                    c["Image"]
                    for c in self.containers()
                    if self.service(c) not in self.safe
                }
            ),
            "consistency": "all Compose API and worker containers stopped; external writers fenced by operator",
            "database": artifact(bundle / "database.dump"),
            "objects": objects,
            "object_count": len(objects),
            "references": refs,
        }
        (bundle / "manifest.json").write_text(json.dumps(manifest, sort_keys=True))
        (bundle / "manifest.sha256").write_text(digest(bundle / "manifest.json") + "\n")
        validate_bundle(bundle, self.c["installation"])
        return manifest

    def owned_snapshots(self):
        snapshots = json.loads(self.restic("snapshots", "--json")) or []
        return [
            s
            for s in snapshots
            if s.get("hostname") == self.c["installation"]
            and set(s.get("tags", [])) == {ENGINE, self.c["installation"]}
        ]

    def retain(self, current):
        def snapshot_time(snapshot):
            return dt.datetime.fromisoformat(snapshot["time"].replace("Z", "+00:00"))

        snapshots = sorted(self.owned_snapshots(), key=snapshot_time, reverse=True)
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(
            days=int(self.c["retention_days"])
        )
        expired = [
            s["id"]
            for s in snapshots[int(self.c["keep_last"]) :]
            if s["id"] != current and snapshot_time(s) < cutoff
        ]
        if expired:
            self.restic("forget", *expired)
            self.restic("prune")
            self.restic("check")

    def backup(self):
        self.check_repository()  # Fail before downtime when vault/keys are unavailable.
        started = time.monotonic()
        with tempfile.TemporaryDirectory(
            prefix="capture-", dir=self.state
        ) as temporary:
            bundle = Path(temporary) / "bundle"
            bundle.mkdir(mode=0o700)
            paused_at = time.monotonic()
            with self.paused():
                manifest = self.capture(bundle)
            downtime = time.monotonic() - paused_at
            output = self.restic(
                "backup",
                "--json",
                "--host",
                self.c["installation"],
                "--tag",
                ENGINE,
                "--tag",
                self.c["installation"],
                "bundle",
                cwd=temporary,
            )
            summaries = [json.loads(line) for line in output.splitlines() if line]
            snapshot = next(
                s["snapshot_id"]
                for s in summaries
                if s.get("message_type") == "summary"
            )
            require(
                re.fullmatch(r"[a-f0-9]{64}", snapshot), "Invalid snapshot identity"
            )
            verify = Path(temporary) / "verified"
            self.restic(
                "restore", snapshot + ":" + SNAPSHOT_ROOT, "--target", str(verify)
            )
            validate_bundle(verify, self.c["installation"])
            self.restic("check")
            self.retain(
                snapshot
            )  # Never expire older backups before remote readback succeeds.
            return {
                "snapshot": snapshot,
                "objects": manifest["object_count"],
                "database_bytes": manifest["database"]["size_bytes"],
                "object_bytes": sum(item["size_bytes"] for item in manifest["objects"]),
                "pause_seconds": round(downtime, 3),
                "total_seconds": round(time.monotonic() - started, 3),
            }

    def restore(self, snapshot):
        require(
            re.fullmatch(r"[a-f0-9]{64}", snapshot), "Use an exact full snapshot ID"
        )
        self.check_repository()
        owned = next((s for s in self.owned_snapshots() if s["id"] == snapshot), None)
        require(
            owned is not None and len(owned["paths"]) == 1,
            "Snapshot is not owned by this mechanism",
        )
        require(not self.writers(), "Stop all target API/workers before restore")
        started = time.monotonic()
        with tempfile.TemporaryDirectory(
            prefix="restore-", dir=self.state
        ) as temporary:
            bundle = Path(temporary) / "bundle"
            self.restic(
                "restore", snapshot + ":" + SNAPSHOT_ROOT, "--target", str(bundle)
            )
            manifest = validate_bundle(bundle, self.c["installation"])
            require(
                manifest["source_project"] != self.project,
                "Refusing restore to source project",
            )
            require(
                manifest["source_storage"] != fingerprint(self.c["storage"]),
                "Refusing restore to source bucket",
            )
            require(self.sql(EMPTY_SQL) == "0", "Target database is not empty")
            client, bucket = self.storage()
            require(not inventory(client, bucket), "Target bucket is not empty")
            versions = client.list_object_versions(Bucket=bucket, MaxKeys=1)
            require(
                not versions.get("Versions") and not versions.get("DeleteMarkers"),
                "Target bucket has object history; use a new bucket",
            )
            for item in manifest["objects"]:
                with (bundle / item["name"]).open("rb") as body:
                    client.put_object(
                        Bucket=bucket,
                        Key=item["key"],
                        Body=body,
                        IfNoneMatch="*",
                        ContentType=item["content_type"],
                        Metadata=item["metadata"],
                    )
                downloaded = Path(temporary) / "readback"
                copy_body(
                    client.get_object(Bucket=bucket, Key=item["key"])["Body"],
                    downloaded,
                )
                require(
                    digest(downloaded) == item["sha256"],
                    "Restored object checksum mismatch",
                )
                downloaded.unlink()
            require(
                set(inventory(client, bucket))
                == {i["key"] for i in manifest["objects"]},
                "Restored object inventory mismatch",
            )
            with (bundle / "database.dump").open("rb") as source:
                run(
                    [
                        *self.compose,
                        "exec",
                        "-T",
                        "postgres",
                        "sh",
                        "-ec",
                        'exec pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-acl --exit-on-error --single-transaction',
                    ],
                    stdin=source,
                )
            require(
                json.loads(self.sql(REFERENCES_SQL)) == manifest["references"],
                "Restored database references differ",
            )
            return {
                "objects": manifest["object_count"],
                "restore_seconds": round(time.monotonic() - started, 3),
            }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("command", choices=("backup", "restore", "resume"))
    parser.add_argument("--snapshot")
    parser.add_argument("--confirm-empty-target", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    try:
        backup = Backup(json.loads(args.config.read_text()))
        with (backup.state / "operation.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if args.command == "backup":
                result = backup.backup()
            elif args.command == "restore":
                require(
                    args.confirm_empty_target and args.snapshot,
                    "Restore requires explicit empty-target confirmation and snapshot",
                )
                result = backup.restore(args.snapshot)
            else:
                backup.resume()
                result = {"resumed": True}
        print(json.dumps({"status": "ok", **result}), flush=True)
        return 0
    except Exception as error:  # noqa: BLE001 -- never expose SDK exception text in production logs.
        # Exception messages from SDKs can include URLs/keys. Keep them private.
        reason = (
            str(error)
            if isinstance(error, BackupError)
            else "Configuration or dependency failure"
        )
        print(
            f"Backup operation failed: {reason}. Check dependency health and resume journal; sensitive diagnostics suppressed.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
