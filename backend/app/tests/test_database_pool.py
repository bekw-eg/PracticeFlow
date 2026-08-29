from app.core.config import settings
from app.db.engine import database_pool_options


def test_api_and_worker_database_pools_are_separate_and_bounded(monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_POOL_SIZE", 10)
    monkeypatch.setattr(settings, "DATABASE_MAX_OVERFLOW", 5)
    monkeypatch.setattr(settings, "DATABASE_POOL_TIMEOUT_SECONDS", 30)
    monkeypatch.setattr(settings, "DATABASE_POOL_RECYCLE_SECONDS", 1800)
    monkeypatch.setattr(settings, "WORKER_DATABASE_POOL_SIZE", 2)
    monkeypatch.setattr(settings, "WORKER_DATABASE_MAX_OVERFLOW", 0)
    monkeypatch.setattr(settings, "WORKER_DATABASE_POOL_TIMEOUT_SECONDS", 15)
    monkeypatch.setattr(settings, "WORKER_DATABASE_POOL_RECYCLE_SECONDS", 1800)

    assert database_pool_options() == {
        "pool_size": 10,
        "max_overflow": 5,
        "pool_timeout": 30,
        "pool_recycle": 1800,
        "pool_pre_ping": True,
    }
    assert database_pool_options(worker=True) == {
        "pool_size": 2,
        "max_overflow": 0,
        "pool_timeout": 15,
        "pool_recycle": 1800,
        "pool_pre_ping": True,
    }
