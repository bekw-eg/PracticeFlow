import threading
import time

from app.rate_limit.base import LoginRateLimiter


class MemoryLoginRateLimiter(LoginRateLimiter):
    """Development/test implementation; production validation rejects it."""

    def __init__(self, attempts: int, window_seconds: int):
        self.attempts = attempts
        self.window_seconds = window_seconds
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _active(self, key: str, now: float) -> list[float]:
        return [item for item in self._failures.get(key, []) if now - item < self.window_seconds]

    def is_blocked(self, key: str) -> bool:
        with self._lock:
            active = self._active(key, time.monotonic())
            self._failures[key] = active
            return len(active) >= self.attempts

    def record_failure(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            self._failures[key] = [*self._active(key, now), now]

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
