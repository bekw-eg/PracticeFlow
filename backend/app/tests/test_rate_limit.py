import redis
import pytest
from fastapi import HTTPException

from app.rate_limit.redis_backend import RedisLoginRateLimiter


class _FakePipeline:
    def __init__(self, client):
        self.client = client
        self.actions = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def incr(self, key):
        self.actions.append(("incr", key))
        return self

    def expire(self, key, seconds, nx=False):
        self.actions.append(("expire", key, seconds, nx))
        return self

    def execute(self):
        for action in self.actions:
            if action[0] == "incr":
                self.client.values[action[1]] = self.client.values.get(action[1], 0) + 1
            elif action[0] == "expire" and action[1] not in self.client.expirations:
                self.client.expirations[action[1]] = action[2]


class _FakeRedis:
    def __init__(self):
        self.values = {}
        self.expirations = {}

    def get(self, key):
        return self.values.get(key)

    def pipeline(self, transaction=True):
        assert transaction is True
        return _FakePipeline(self)

    def delete(self, key):
        self.values.pop(key, None)

    def ping(self):
        return True


def test_redis_rate_limit_state_is_shared_between_replicas():
    shared_redis = _FakeRedis()
    replica_a = RedisLoginRateLimiter("redis://unused", attempts=2, window_seconds=60)
    replica_b = RedisLoginRateLimiter("redis://unused", attempts=2, window_seconds=60)
    replica_a.client = shared_redis
    replica_b.client = shared_redis

    replica_a.record_failure("identity")
    assert replica_b.is_blocked("identity") is False
    replica_b.record_failure("identity")
    assert replica_a.is_blocked("identity") is True
    assert shared_redis.expirations["practiceflow:login-failures:identity"] == 60

    replica_a.reset("identity")
    assert replica_b.is_blocked("identity") is False


def test_redis_login_limiter_fails_closed_with_a_controlled_503():
    class UnavailableRedis:
        def get(self, _key):
            raise redis.ConnectionError("maxmemory reached")

    limiter = RedisLoginRateLimiter("redis://unused", attempts=2, window_seconds=60)
    limiter.client = UnavailableRedis()

    with pytest.raises(HTTPException) as unavailable:
        limiter.is_blocked("identity")

    assert unavailable.value.status_code == 503


def test_redis_login_limiter_fails_closed_when_noeviction_rejects_a_write():
    class MaxMemoryRedis:
        def pipeline(self, **_kwargs):
            raise redis.ResponseError("OOM command not allowed when used memory > 'maxmemory'.")

    limiter = RedisLoginRateLimiter("redis://unused", attempts=2, window_seconds=60)
    limiter.client = MaxMemoryRedis()

    with pytest.raises(HTTPException) as unavailable:
        limiter.record_failure("identity")

    assert unavailable.value.status_code == 503
