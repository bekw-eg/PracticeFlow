"""Reviewed SQLAlchemy engine factories shared without creating an API engine."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.core.config import settings


def database_pool_options(*, worker: bool = False) -> dict[str, int | bool]:
    """Return bounded QueuePool options for an API replica or export worker."""
    if worker:
        return {
            "pool_size": settings.WORKER_DATABASE_POOL_SIZE,
            "max_overflow": settings.WORKER_DATABASE_MAX_OVERFLOW,
            "pool_timeout": settings.WORKER_DATABASE_POOL_TIMEOUT_SECONDS,
            "pool_recycle": settings.WORKER_DATABASE_POOL_RECYCLE_SECONDS,
            "pool_pre_ping": True,
        }
    return {
        "pool_size": settings.DATABASE_POOL_SIZE,
        "max_overflow": settings.DATABASE_MAX_OVERFLOW,
        "pool_timeout": settings.DATABASE_POOL_TIMEOUT_SECONDS,
        "pool_recycle": settings.DATABASE_POOL_RECYCLE_SECONDS,
        "pool_pre_ping": True,
    }


def create_database_engine(database_url: str | None = None, *, worker: bool = False) -> Engine:
    """Create a bounded engine without importing the API session module."""
    return create_engine(database_url or settings.DATABASE_URL, future=True, **database_pool_options(worker=worker))
