import io

from app.services.storage_migration import LocalToS3Migrator, StorageMigrationCandidate
from app.storage.base import StorageService
from app.storage.local import LocalStorageService


class MemoryObjectStorage(StorageService):
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def save(self, key, data, content_type):
        self.objects[key] = data.read()
        return key

    def get(self, key):
        if key not in self.objects:
            raise FileNotFoundError(key)
        return self.objects[key]

    def open(self, key):
        return io.BytesIO(self.get(key))

    def delete(self, key):
        self.objects.pop(key, None)

    def exists(self, key):
        return key in self.objects

    def ping(self):
        return True


def _candidate() -> StorageMigrationCandidate:
    return StorageMigrationCandidate(
        key="orgs/11111111-1111-1111-1111-111111111111/images/22222222-2222-2222-2222-222222222222.png",
        content_type="image/png",
        expected_size_bytes=12,
        source="file",
    )


def _migrator(tmp_path):
    source = LocalStorageService(str(tmp_path / "local"))
    source.save(_candidate().key, io.BytesIO(b"source-bytes"), "image/png")
    return source, MemoryObjectStorage()


def test_migration_dry_run_does_not_write_objects(tmp_path):
    source, destination = _migrator(tmp_path)

    report = LocalToS3Migrator(source, destination).migrate([_candidate()], dry_run=True)

    assert report.transferred == []
    assert len(report.would_transfer) == 1
    assert destination.objects == {}
    assert source.exists(_candidate().key)


def test_migration_is_idempotent_after_checksum_verified_copy(tmp_path):
    source, destination = _migrator(tmp_path)
    migrator = LocalToS3Migrator(source, destination)

    first = migrator.migrate([_candidate()], dry_run=False)
    second = migrator.migrate([_candidate()], dry_run=False)

    assert len(first.transferred) == 1
    assert first.errors == []
    assert len(second.skipped) == 1
    assert second.errors == []
    assert source.exists(_candidate().key)  # source is never deleted


def test_migration_refuses_destination_checksum_mismatch(tmp_path):
    source, destination = _migrator(tmp_path)
    destination.save(_candidate().key, io.BytesIO(b"wrong-object!"), "image/png")

    report = LocalToS3Migrator(source, destination).migrate([_candidate()], dry_run=False)

    assert report.transferred == []
    assert report.errors[0]["reason"] == "destination_checksum_mismatch"
    assert destination.get(_candidate().key) == b"wrong-object!"
