"""Redis delivery queue for durable export jobs.

PostgreSQL is the job source of truth; duplicate/stale messages are harmless
because workers claim only rows still in ``queued`` state.
"""
from __future__ import annotations

import queue
from abc import ABC, abstractmethod
from typing import cast

import redis
from fastapi import HTTPException, status

from app.observability.metrics import metrics


class ExportQueue(ABC):
    @abstractmethod
    def enqueue(self, job_id: str) -> None:
        ...

    @abstractmethod
    def dequeue(self, timeout_seconds: int) -> str | None:
        ...

    def ping(self) -> bool:
        return True

    @abstractmethod
    def depth(self) -> int:
        ...


def _unavailable() -> HTTPException:
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Export queue is temporarily unavailable.")


class MemoryExportQueue(ExportQueue):
    """Only for single-process tests. Compose development uses Redis too."""

    def __init__(self):
        self.items: queue.Queue[str] = queue.Queue()

    def enqueue(self, job_id: str) -> None:
        self.items.put_nowait(job_id)

    def dequeue(self, timeout_seconds: int) -> str | None:
        try:
            return self.items.get(timeout=timeout_seconds)
        except queue.Empty:
            return None

    def depth(self) -> int:
        return self.items.qsize()


class RedisExportQueue(ExportQueue):
    key = "practiceflow:export-jobs"

    def __init__(self, url: str):
        # BRPOP intentionally blocks up to EXPORT_WORKER_QUEUE_TIMEOUT_SECONDS.
        # A shorter generic socket timeout would turn every empty queue into a
        # false 503 and a noisy retry loop. Connection establishment remains
        # bounded; BRPOP itself supplies the read deadline.
        self.client = redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=2, socket_timeout=None)

    def enqueue(self, job_id: str) -> None:
        try:
            self.client.lpush(self.key, job_id)
        except redis.RedisError as exc:
            metrics.observe_dependency("redis_export_queue", "failure")
            raise _unavailable() from exc
        metrics.observe_dependency("redis_export_queue", "success")

    def dequeue(self, timeout_seconds: int) -> str | None:
        try:
            item = cast(list[str] | None, self.client.brpop([self.key], timeout=timeout_seconds))
        except redis.RedisError as exc:
            metrics.observe_dependency("redis_export_queue", "failure")
            raise _unavailable() from exc
        metrics.observe_dependency("redis_export_queue", "success")
        return item[1] if item else None

    def depth(self) -> int:
        try:
            # This is the synchronous redis client; redis-py's shared
            # sync/async type surface otherwise exposes an Awaitable union.
            value = int(cast(int, self.client.llen(self.key)))
        except redis.RedisError as exc:
            metrics.observe_dependency("redis_export_queue", "failure")
            raise _unavailable() from exc
        metrics.observe_dependency("redis_export_queue", "success")
        return value

    def ping(self) -> bool:
        try:
            available = bool(self.client.ping())
        except redis.RedisError:
            available = False
        metrics.observe_dependency("redis_export_queue", "success" if available else "failure")
        return available
