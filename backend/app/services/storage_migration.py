"""Idempotent migration of metadata-backed LocalStorage objects into S3."""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import BinaryIO, Iterable

from app.storage.base import StorageService
from app.storage.local import LocalStorageService


CHECKSUM_CHUNK_BYTES = 64 * 1024


@dataclass(frozen=True)
class StorageMigrationCandidate:
    key: str
    content_type: str
    expected_size_bytes: int | None
    source: str


@dataclass
class StorageMigrationReport:
    dry_run: bool
    transferred: list[dict] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    would_transfer: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def _digest(stream: BinaryIO) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(CHECKSUM_CHUNK_BYTES):
        size += len(chunk)
        digest.update(chunk)
    return size, digest.hexdigest()


class LocalToS3Migrator:
    """Copy only DB-referenced bytes and never delete the LocalStorage source."""

    def __init__(self, source: LocalStorageService, destination: StorageService):
        self.source = source
        self.destination = destination

    @staticmethod
    def _entry(candidate: StorageMigrationCandidate, size_bytes: int, checksum_sha256: str) -> dict:
        return {
            "key": candidate.key,
            "source": candidate.source,
            "size_bytes": size_bytes,
            "checksum_sha256": checksum_sha256,
        }

    def _checksum_source(self, candidate: StorageMigrationCandidate) -> tuple[int, str]:
        with self.source.open(candidate.key) as stream:
            return _digest(stream)

    def _checksum_destination(self, candidate: StorageMigrationCandidate) -> tuple[int, str]:
        stream = self.destination.open(candidate.key)
        try:
            return _digest(stream)
        finally:
            stream.close()

    def migrate(self, candidates: Iterable[StorageMigrationCandidate], *, dry_run: bool) -> StorageMigrationReport:
        report = StorageMigrationReport(dry_run=dry_run)
        for candidate in candidates:
            try:
                source_size, source_checksum = self._checksum_source(candidate)
                entry = self._entry(candidate, source_size, source_checksum)
                if candidate.expected_size_bytes is not None and source_size != candidate.expected_size_bytes:
                    report.errors.append({**entry, "reason": "source_size_mismatch"})
                    continue

                if self.destination.exists(candidate.key):
                    target_size, target_checksum = self._checksum_destination(candidate)
                    if (target_size, target_checksum) == (source_size, source_checksum):
                        report.skipped.append(entry)
                    else:
                        # Never overwrite an object under a key whose bytes do
                        # not prove equal to the local source. This makes a
                        # repeated run safe even after an operator incident.
                        report.errors.append({**entry, "reason": "destination_checksum_mismatch"})
                    continue

                if dry_run:
                    report.would_transfer.append(entry)
                    continue

                with self.source.open(candidate.key) as stream:
                    self.destination.save(candidate.key, stream, candidate.content_type)
                target_size, target_checksum = self._checksum_destination(candidate)
                if (target_size, target_checksum) != (source_size, source_checksum):
                    report.errors.append({**entry, "reason": "post_upload_checksum_mismatch"})
                    continue
                report.transferred.append(entry)
            except Exception as exc:
                # The report deliberately has a stable reason only; storage
                # exception detail can reveal deployment endpoints/credentials.
                report.errors.append({"key": candidate.key, "source": candidate.source, "reason": type(exc).__name__})
        return report
