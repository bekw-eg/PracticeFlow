"""Safe, bounded Redis memory sampling for the Prometheus endpoint."""
from __future__ import annotations

from typing import cast

import redis

from app.core.config import settings
from app.observability.metrics import metrics


def observe_redis_memory() -> None:
    """Record only aggregate memory counters; never expose keys or values."""
    if not settings.REDIS_URL:
        return
    try:
        client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=2, socket_timeout=2)
        # redis-py exposes sync/async-compatible typing here. This client is
        # explicitly synchronous; cast only the aggregate INFO mapping.
        memory = cast(dict[str, str | int], client.info(section="memory"))
        metrics.set_redis_memory(
            used_bytes=int(memory.get("used_memory", 0)),
            max_bytes=int(memory.get("maxmemory", 0)),
        )
        metrics.observe_dependency("redis_memory", "success")
    except (redis.RedisError, TypeError, ValueError):
        metrics.observe_dependency("redis_memory", "failure")
