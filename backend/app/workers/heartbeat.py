"""Low-cardinality export-worker liveness signal backed by Redis.

Worker identifiers are internal Redis members only; public metrics expose only
a count and newest age, never an identifier.
"""
from __future__ import annotations

import os
import socket
import time
from abc import ABC, abstractmethod
from functools import lru_cache
from threading import Lock

import redis

from app.core.config import settings
from app.observability.metrics import metrics


class WorkerHeartbeat(ABC):
    @abstractmethod
    def beat(self, worker_id: str) -> None:
        ...

    @abstractmethod
    def snapshot(self) -> tuple[float | None, int]:
        """Return newest heartbeat age and active worker count."""
        ...


class MemoryWorkerHeartbeat(WorkerHeartbeat):
    def __init__(self) -> None:
        self._beats: dict[str, float] = {}
        self._lock = Lock()

    def beat(self, worker_id: str) -> None:
        with self._lock:
            self._beats[worker_id] = time.time()

    def snapshot(self) -> tuple[float | None, int]:
        cutoff = time.time() - settings.EXPORT_WORKER_HEARTBEAT_TTL_SECONDS
        with self._lock:
            self._beats = {worker_id: stamp for worker_id, stamp in self._beats.items() if stamp >= cutoff}
            if not self._beats:
                return None, 0
            return max(0.0, time.time() - max(self._beats.values())), len(self._beats)


class RedisWorkerHeartbeat(WorkerHeartbeat):
    key = "practiceflow:export-worker:heartbeats"

    def __init__(self, url: str) -> None:
        self.client = redis.Redis.from_url(url, decode_responses=True, socket_timeout=2)

    def beat(self, worker_id: str) -> None:
        now = time.time()
        try:
            self.client.zadd(self.key, {worker_id: now})
            self.client.zremrangebyscore(self.key, "-inf", now - settings.EXPORT_WORKER_HEARTBEAT_TTL_SECONDS)
            self.client.expire(self.key, settings.EXPORT_WORKER_HEARTBEAT_TTL_SECONDS * 2)
            metrics.observe_dependency("redis_worker_heartbeat", "success")
        except redis.RedisError:
            metrics.observe_dependency("redis_worker_heartbeat", "failure")
            raise

    def snapshot(self) -> tuple[float | None, int]:
        now = time.time()
        try:
            self.client.zremrangebyscore(self.key, "-inf", now - settings.EXPORT_WORKER_HEARTBEAT_TTL_SECONDS)
            newest = self.client.zrevrange(self.key, 0, 0, withscores=True)
            active = self.client.zcard(self.key)
            metrics.observe_dependency("redis_worker_heartbeat", "success")
        except redis.RedisError:
            metrics.observe_dependency("redis_worker_heartbeat", "failure")
            return None, 0
        if not newest:
            return None, int(active)
        return max(0.0, now - float(newest[0][1])), int(active)


def default_worker_id() -> str:
    # This value stays in Redis and structured worker logs, never metrics labels.
    return f"{socket.gethostname()}-{os.getpid()}"


@lru_cache
def get_worker_heartbeat() -> WorkerHeartbeat:
    if settings.EXPORT_QUEUE_BACKEND == "redis":
        if not settings.REDIS_URL:
            raise RuntimeError("REDIS_URL is required for the export-worker heartbeat")
        return RedisWorkerHeartbeat(settings.REDIS_URL)
    return MemoryWorkerHeartbeat()
