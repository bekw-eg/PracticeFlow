import redis
from fastapi import HTTPException, status

from app.observability.metrics import metrics
from app.rate_limit.base import LoginRateLimiter


class RedisLoginRateLimiter(LoginRateLimiter):
    """Fixed-window limiter shared atomically by every application replica."""

    def __init__(self, url: str, attempts: int, window_seconds: int, key_namespace: str = "login-failures"):
        self.attempts = attempts
        self.window_seconds = window_seconds
        self.client = redis.Redis.from_url(url, decode_responses=True, socket_timeout=2)
        self.key_namespace = key_namespace

    def _redis_key(self, key: str) -> str:
        return f"practiceflow:{self.key_namespace}:{key}"

    @staticmethod
    def _unavailable(exc: redis.RedisError) -> HTTPException:
        metrics.observe_dependency("redis_rate_limit", "failure")
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Login protection is temporarily unavailable.")

    def is_blocked(self, key: str) -> bool:
        try:
            value = self.client.get(self._redis_key(key))
        except redis.RedisError as exc:
            raise self._unavailable(exc) from exc
        metrics.observe_dependency("redis_rate_limit", "success")
        return int(str(value or 0)) >= self.attempts

    def record_failure(self, key: str) -> None:
        redis_key = self._redis_key(key)
        try:
            with self.client.pipeline(transaction=True) as pipeline:
                pipeline.incr(redis_key)
                pipeline.expire(redis_key, self.window_seconds, nx=True)
                pipeline.execute()
        except redis.RedisError as exc:
            raise self._unavailable(exc) from exc
        metrics.observe_dependency("redis_rate_limit", "success")

    def reset(self, key: str) -> None:
        try:
            self.client.delete(self._redis_key(key))
        except redis.RedisError as exc:
            raise self._unavailable(exc) from exc
        metrics.observe_dependency("redis_rate_limit", "success")

    def ping(self) -> bool:
        try:
            available = bool(self.client.ping())
        except redis.RedisError:
            available = False
        metrics.observe_dependency("redis_rate_limit", "success" if available else "failure")
        return available
