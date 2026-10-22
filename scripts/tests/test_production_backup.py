"""Security/failure invariants; no production data or infrastructure required."""

import contextlib
import fcntl
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import production_backup as pb


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.config = {
            "installation": "test-installation",
            "project": "pf-backup-test-unit",
            "test_mode": True,
            "state_directory": str(self.root / "state"),
            "compose_files": ["unused.yml"],
            "retention_days": 30,
            "keep_last": 1,
            "storage": {"endpoint": "https://source.invalid", "bucket": "source"},
        }
        self.backup = pb.Backup(self.config)

    def tearDown(self):
        self.tmp.cleanup()

    def bundle(self):
        bundle = self.root / "bundle"
        bundle.mkdir()
        (bundle / "database.dump").write_bytes(b"synthetic database")
        (bundle / "object-00000000").write_bytes(b"synthetic document")
        obj = {
            **pb.artifact(bundle / "object-00000000"),
            "key": "orgs/fixture/document",
        }
        manifest = {
            "engine": pb.ENGINE,
            "installation": "test-installation",
            "database": pb.artifact(bundle / "database.dump"),
            "objects": [obj],
            "object_count": 1,
            "references": [{"key": obj["key"], "size_bytes": obj["size_bytes"]}],
        }
        self.write_manifest(bundle, manifest)
        return bundle, manifest

    @staticmethod
    def write_manifest(bundle, manifest):
        (bundle / "manifest.json").write_text(json.dumps(manifest))
        (bundle / "manifest.sha256").write_text(pb.digest(bundle / "manifest.json"))

    def test_complete_manifest(self):
        bundle, _ = self.bundle()
        self.assertEqual(
            pb.validate_bundle(bundle, "test-installation")["object_count"], 1
        )

    def test_corrupted_missing_extra_and_wrong_installation_rejected(self):
        bundle, _ = self.bundle()
        with self.assertRaises(RuntimeError):
            pb.validate_bundle(bundle, "different-installation")
        (bundle / ".env").write_text("must never be archived")
        with self.assertRaises(RuntimeError):
            pb.validate_bundle(bundle, "test-installation")
        (bundle / ".env").unlink()
        (bundle / "object-00000000").write_bytes(b"corruption")
        with self.assertRaises(RuntimeError):
            pb.validate_bundle(bundle, "test-installation")
        (bundle / "object-00000000").unlink()
        with self.assertRaises(RuntimeError):
            pb.validate_bundle(bundle, "test-installation")

    def test_traversal_and_missing_reference_rejected(self):
        bundle, manifest = self.bundle()
        manifest["references"][0]["key"] = "missing"
        self.write_manifest(bundle, manifest)
        with self.assertRaises(RuntimeError):
            pb.validate_bundle(bundle, "test-installation")
        manifest["objects"][0]["name"] = "../outside"
        self.write_manifest(bundle, manifest)
        with self.assertRaises(RuntimeError):
            pb.validate_bundle(bundle, "test-installation")

    def test_zero_retention_and_test_mode_on_production_rejected(self):
        for overrides in (
            {"keep_last": 0},
            {"retention_days": 0},
            {"project": "production"},
        ):
            with self.assertRaises(RuntimeError):
                pb.Backup({**self.config, **overrides})

    def test_repository_identity_checked(self):
        self.backup.c["repository_id"] = "expected"
        password = self.root / "password"
        password.write_text("test-only-password")
        password.chmod(0o600)
        self.backup.c["password_file"] = str(password)
        with (
            patch.object(self.backup, "restic", return_value=b'{"id":"wrong"}'),
            self.assertRaises(RuntimeError),
        ):
            self.backup.check_repository()

    def test_production_insecure_or_source_endpoint_vault_rejected(self):
        self.backup.test = False
        for repository in (
            "/local/repository",
            "s3:http://vault.invalid/bucket",
            "s3:https://source.invalid/vault",
        ):
            self.backup.c["repository"] = repository
            with self.assertRaises(RuntimeError):
                self.backup.restic("check")

    def test_command_diagnostics_do_not_expose_secrets(self):
        completed = __import__("subprocess").CompletedProcess(
            [], 1, stdout=b"private document", stderr=b"secret token"
        )
        with patch.object(pb.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(
                RuntimeError, "sensitive output suppressed"
            ) as error:
                pb.run(["test"])
            self.assertNotIn("secret token", str(error.exception))

    def test_retention_filters_foreign_and_preserves_minimum(self):
        own = {
            "hostname": "test-installation",
            "tags": [pb.ENGINE, "test-installation"],
        }
        snapshots = [
            {**own, "id": "new", "time": "2026-10-21T00:00:00Z"},
            {**own, "id": "old", "time": "2001-01-01T00:00:00Z"},
            {
                **own,
                "id": "foreign",
                "tags": ["unrelated"],
                "time": "2000-01-01T00:00:00Z",
            },
        ]
        calls = []

        def restic(*args):
            calls.append(args)
            return json.dumps(snapshots).encode() if args[0] == "snapshots" else b""

        with patch.object(self.backup, "restic", side_effect=restic):
            self.backup.retain("new")
        self.assertIn(("forget", "old"), calls)
        self.assertIn(("check",), calls)
        self.assertFalse(any("foreign" in args for args in calls))

    def test_failed_remote_readback_never_runs_retention(self):
        @contextlib.contextmanager
        def paused():
            yield

        summary = json.dumps(
            {"message_type": "summary", "snapshot_id": "a" * 64}
        ).encode()

        def restic(*args, **kwargs):
            if args[0] == "restore":
                raise RuntimeError("failed readback")
            return summary

        with (
            patch.object(self.backup, "check_repository"),
            patch.object(self.backup, "paused", paused),
            patch.object(self.backup, "capture", return_value={"object_count": 1}),
            patch.object(self.backup, "restic", side_effect=restic),
            patch.object(self.backup, "retain") as retain,
        ):
            with self.assertRaises(RuntimeError):
                self.backup.backup()
            retain.assert_not_called()

    def test_restart_error_is_not_success_and_retains_journal(self):
        self.backup.journal.write_text(
            json.dumps({"project": self.backup.project, "ids": ["writer"]})
        )
        container = {
            "Id": "writer",
            "Config": {"Labels": {"com.docker.compose.service": "backend"}},
        }
        with (
            patch.object(self.backup, "containers", return_value=[container]),
            patch.object(pb, "run", side_effect=RuntimeError("start failed")),
            self.assertRaises(RuntimeError),
        ):
            self.backup.resume()
        self.assertTrue(self.backup.journal.exists())

    def test_cli_suppresses_sdk_exception_content(self):
        config = self.root / "config.json"
        config.write_text(json.dumps(self.config))
        output = io.StringIO()
        with (
            patch.object(sys, "argv", ["backup", "--config", str(config), "backup"]),
            patch.object(
                pb.Backup, "backup", side_effect=RuntimeError("secret credential")
            ),
            contextlib.redirect_stderr(output),
        ):
            self.assertEqual(pb.main(), 1)
        self.assertNotIn("secret credential", output.getvalue())

    def test_another_process_cannot_enter_the_operation_lock(self):
        config = self.root / "config.json"
        config.write_text(json.dumps(self.config))
        child = (
            "import sys; from unittest.mock import patch; import production_backup as pb; "
            "sys.argv=['backup','--config',sys.argv[1],'backup']; "
            "p=patch.object(pb.Backup,'backup',return_value={'mock':True}); p.start(); sys.exit(pb.main())"
        )
        with (self.backup.state / "operation.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            blocked = subprocess.run(
                [sys.executable, "-c", child, str(config)],
                cwd=Path(pb.__file__).parent,
                capture_output=True,
                check=False,
            )
            self.assertEqual(blocked.returncode, 1)
            self.assertFalse(blocked.stdout)
        unblocked = subprocess.run(
            [sys.executable, "-c", child, str(config)],
            cwd=Path(pb.__file__).parent,
            capture_output=True,
            check=False,
        )
        self.assertEqual(unblocked.returncode, 0)

    def test_partial_stop_failure_resumes_original_writers(self):
        def writer(service):
            return {
                "Id": service,
                "Config": {
                    "Labels": {"com.docker.compose.service": service},
                    "Env": [
                        "STORAGE_BACKEND=s3",
                        "DATABASE_URL=postgresql://user@postgres/database",
                        "S3_ENDPOINT_URL=https://source.invalid",
                        "S3_BUCKET=source",
                    ],
                },
            }

        writers = [
            writer("export-worker"),
            writer("document-check-worker"),
            writer("backend"),
        ]
        pg = {
            "Id": "pg",
            "Config": {
                "Labels": {"com.docker.compose.service": "postgres"},
                "Env": ["POSTGRES_DB=database"],
            },
        }
        calls = []

        def stop(args):
            calls.append(args)
            if args[-1] == "document-check-worker":
                raise RuntimeError("failed to stop")
            return b""

        with (
            patch.object(self.backup, "writers", return_value=writers),
            patch.object(self.backup, "containers", return_value=[*writers, pg]),
            patch.object(pb, "run", side_effect=stop),
            patch.object(self.backup, "resume") as resume,
        ):
            with self.assertRaises(RuntimeError), self.backup.paused():
                self.fail("Capture must not start after a stop failure")
            resume.assert_called_once()
        self.assertEqual(calls[0][-1], "backend")
        self.assertEqual(
            set(json.loads(self.backup.journal.read_text())["ids"]),
            {"backend", "export-worker", "document-check-worker"},
        )

    def test_real_restic_relative_tree_roundtrip(self):
        fixture, manifest = self.bundle()
        password = self.root / "password"
        password.write_text("synthetic-roundtrip-password")
        password.chmod(0o600)
        self.backup.c.update(
            repository=str(self.root / "repository"),
            password_file=str(password),
            vault_access_key_env="PF_TEST_ACCESS",
            vault_secret_key_env="PF_TEST_SECRET",
            vault_region="us-east-1",
        )

        @contextlib.contextmanager
        def paused():
            yield

        def capture(bundle):
            for path in fixture.iterdir():
                shutil.copyfile(path, bundle / path.name)
            return manifest

        with (
            patch.dict(
                os.environ,
                {"PF_TEST_ACCESS": "synthetic", "PF_TEST_SECRET": "synthetic"},
            ),
            patch.object(self.backup, "paused", paused),
            patch.object(self.backup, "capture", side_effect=capture),
        ):
            self.backup.restic("init")
            self.backup.c["repository_id"] = json.loads(
                self.backup.restic("cat", "config")
            )["id"]
            result = self.backup.backup()
            restored = self.root / "restored"
            self.backup.restic(
                "restore",
                result["snapshot"] + ":" + pb.SNAPSHOT_ROOT,
                "--target",
                str(restored),
            )
            self.assertEqual(
                pb.validate_bundle(restored, "test-installation"), manifest
            )
            self.assertEqual(result["objects"], 1)


if __name__ == "__main__":
    unittest.main()
